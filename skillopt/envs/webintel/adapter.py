"""Web Intelligence environment adapter for SkillOpt with TDAI shared memory.

Optimizes the Web Intelligence routing skill for web automation tasks.
The skill is evaluated by sending queries and scoring the quality of responses.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import urllib.request
from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.envs.webintel.dataloader import WebIntelDataLoader
from skillopt.envs.webintel.rubric_scoring import score_with_rubric, WEBINTEL_FULL_RUBRIC
from skillopt.envs.webintel.dsh_judge import dsh_score_response, dsh_available
from skillopt.envs.webintel.nvidia_judge import nvidia_score_response, nvidia_available


# ── TDAI Gateway Integration ──────────────────────────────────────────────────

TDAI_GATEWAY = "http://127.0.0.1:8420"
TDAI_NAMESPACE = "hermes-shared-memory"


def _tdai_key():
    path = os.path.expanduser("~/.memory-tencentdb/.gateway-key")
    with open(path) as f:
        return f.read().strip()


def _tdai_post(path, payload):
    key = _tdai_key()
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{TDAI_GATEWAY}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "x-tdai-service-id": TDAI_NAMESPACE,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def tdai_read_context(query="webintel queries generation prompts research"):
    try:
        result = _tdai_post("/v2/atomic/search", {"query": query, "limit": 10})
        items = result.get("data", {}).get("items", [])
        if not items:
            return ""
        lines = ["[TDAI Shared Memory — patterns learned by other agents]"]
        for item in items:
            content = item.get("content", "").strip()
            if content:
                lines.append(f"  - {content[:300]}")
        return "\n".join(lines)
    except Exception:
        return ""


def tdai_write_memory(content):
    try:
        _tdai_post("/v2/core/write", {"content": content, "type": "skillopt-webintel"})
        return True
    except Exception:
        return False


def tdai_search(query, limit=5):
    try:
        result = _tdai_post("/v2/atomic/search", {"query": query, "limit": limit})
        return result.get("data", {}).get("items", [])
    except Exception:
        return []


class WebIntelAdapter(EnvAdapter):
    def __init__(self, split_dir="", data_path="", split_mode="split_dir",
                 split_ratio="2:1:7", split_seed=42, split_output_dir="",
                 workers=4, analyst_workers=4, failure_only=False,
                 minibatch_size=8, edit_budget=4, seed=42, limit=0,
                 max_completion_tokens=4096, use_dsh_judge=False, **kwargs):
        self.workers = workers
        self.analyst_workers = analyst_workers
        self.failure_only = failure_only
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.max_completion_tokens = int(max_completion_tokens)
        self.use_dsh_judge = bool(use_dsh_judge)
        self.dsh_judge_available = dsh_available() if self.use_dsh_judge else False
        if self.use_dsh_judge and not self.dsh_judge_available:
            print("  [WARN] use_dsh_judge=true but dsh-coder not found; falling back to keyword scoring")
        # NVIDIA Nemotron Super judge (preferred — all-NVIDIA, no DSH dep).
        self.nvidia_judge_available = nvidia_available() if self.use_dsh_judge else False
        if self.use_dsh_judge and not self.nvidia_judge_available:
            print("  [WARN] use_dsh_judge=true but NVIDIA judge unreachable; falling back to keyword scoring")
        self.dataloader = WebIntelDataLoader(
            split_dir=split_dir, data_path=data_path, split_mode=split_mode,
            split_ratio=split_ratio, split_seed=split_seed,
            split_output_dir=split_output_dir, seed=seed, limit=limit)
        self._tdai_cache = None

    def setup(self, cfg):
        super().setup(cfg)
        self.dataloader.setup(cfg)

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch, **kwargs):
        return list(batch.payload or [])

    def build_train_env(self, batch_size, seed, **kwargs):
        batch = self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def build_eval_env(self, env_num, split, seed, **kwargs):
        batch = self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def get_merged_skill(self) -> str:
        """Get the combined template + site config skill."""
        return self.dataloader.get_merged_skill()

    def _get_tdai_context(self):
        if self._tdai_cache is None:
            self._tdai_cache = tdai_read_context()
            if self._tdai_cache:
                print(f"  [TDAI] Loaded {len(self._tdai_cache)} chars of shared memory context")
        return self._tdai_cache

    def rollout(self, env_manager, skill_content, out_dir, **kwargs):
        """Roll out the skill on WebIntel tasks.

        Uses the merged skill (template + site config) from the dataloader.
        """
        from skillopt.model import chat_target
        items = env_manager
        results = []
        os.makedirs(os.path.join(out_dir, "predictions"), exist_ok=True)

        tdai_ctx = self._get_tdai_context()

        # Get merged skill (template + site config) for system prompt
        merged_skill = self.get_merged_skill() or skill_content

        # Extract site info from merged skill for context
        site_context = ""
        if "Site-Specific Configuration" in merged_skill:
            site_part = merged_skill.split("Site-Specific Configuration")[-1]
            site_context = f"\n\nSITE CONTEXT:\n{site_part[:2000]}"

        if tdai_ctx:
            system_msg = (
                f"You are an agent doing web intelligence tasks. "
                f"Follow the routing rules and site-specific guidance to pick the correct tool and commands.\n\n"
                f"SKILL:\n{merged_skill}{site_context}\n\n"
                f"{tdai_ctx}"
            )
        else:
            system_msg = (
                f"You are an agent doing web intelligence tasks. "
                f"Follow the routing rules and site-specific guidance to pick the correct tool and commands.\n\n"
                f"SKILL:\n{merged_skill}{site_context}"
            )

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _process_item(item):
            iid = item["id"]
            pred_dir = os.path.join(out_dir, "predictions", iid)
            os.makedirs(pred_dir, exist_ok=True)

            user_msg = item["question"]

            try:
                response_text, _usage = chat_target(
                    system=system_msg,
                    user=user_msg,
                    max_completion_tokens=self.max_completion_tokens,
                    stage="rollout",
                )
                text = response_text if isinstance(response_text, str) else str(response_text)
            except Exception as e:
                text = f"ERROR: {e}"

            # Granular rubric scoring (task-type aware + site-specific)
            task_type = item.get("task_type", "routing")
            site = item.get("site", "")
            check = item.get("check") or []
            if check:
                # Per-item ground-truth patterns (check/must_not/optional) are the
                # authoritative signal. The rubric (keyword OR DSH judge) is a
                # coarse fallback and, for items tagged with a generic task_type
                # like "webintel", scores against the FULL 28-criterion rubric ->
                # every answer hard=0.0 and the validation gate rejects
                # everything. Use the hardened token-aware scorer when check
                # patterns exist.
                from skillopt.envs.scoring import score_response
                sc = score_response(
                    text,
                    check=check,
                    must_not=item.get("must_not"),
                    optional=item.get("optional"),
                )
                sc["rubric_score"] = sc["soft"]
                sc["penalty"] = 0.0
                sc["criteria_met"] = len(sc["matched"])
                sc["criteria_total"] = len(check)
                sc["anti_patterns"] = len(sc["violations"])
                sc["criteria_details"] = [
                    {"criterion": p, "met": p in sc["matched"]} for p in check
                ]
                sc["judge"] = "check-patterns"

                # HARDENED: use the NVIDIA Nemotron Super judge as a semantic
                # tiebreaker on PARTIAL matches (0 < soft < 1) — exactly where
                # token matching is ambiguous and a semantic judge adds signal.
                # Falls back to the check-pattern score on any failure.
                if (
                    self.use_dsh_judge
                    and self.nvidia_judge_available
                    and 0.0 < sc["soft"] < 1.0
                ):
                    nv = nvidia_score_response(text, task_type=task_type, site=site)
                    if not nv.get("fallback", False):
                        # Blend: keep the token signal but let the judge refine
                        # the partial-match items. Weight 0.5 so it can move a
                        # 0.5 partial to 0.75 but never fully override a clear
                        # token miss (soft stays < 1.0 unless judge is confident).
                        sc["soft"] = 0.5 * sc["soft"] + 0.5 * nv.get("soft", sc["soft"])
                        sc["hard"] = 1.0 if sc["soft"] >= 0.6 else 0.0
                        sc["judge"] = "check-patterns+nvidia-super"
                        sc["nvidia_soft"] = nv.get("soft", 0.0)
            elif self.use_dsh_judge and self.nvidia_judge_available:
                sc = nvidia_score_response(text, task_type=task_type, site=site)
            else:
                sc = score_with_rubric(text, task_type=task_type, site=site)
            # HARDENED: score_response() returns `soft`/`hard`, NOT `score`.
            # Using sc.get("score", 0.0) silently zeroed every soft score (and
            # cascaded into hard via the penalty blocks below), making the
            # validation gate reject every candidate. Use the real soft score.
            score = sc.get("soft", 0.0)
            # hard = true pattern-match correctness from the scorer. Penalties
            # below reduce `score` (soft) only; they must NOT overwrite hard,
            # otherwise a fully-correct answer gets hard=0.0 just for a quality
            # flag, and the gate (hard metric) rejects it.
            hard = sc.get("hard", 1.0 if score >= 0.6 else 0.0)

            # HARDENED sanity guard: a non-zero hard with a zero soft is
            # impossible (hard is derived from soft) and signals a broken
            # scorer contract. Surface it loudly instead of silently feeding
            # the gate a corrupted score.
            if hard > 0.0 and score <= 0.0:
                print(
                    f"    [WARN] {iid}: hard={hard} but soft={score} — "
                    f"scorer contract broken (missing 'soft' key?)"
                )

            # Anti-slop quality gate: deterministic mechanical-defect scan
            # (residue, placeholders, fabricated refs). Penalize responses that
            # contain these defects. Absorbed from AgriciDaniel/anti-slop.
            anti_slop = {"ok": True, "count": 0, "findings": []}
            try:
                from skillopt.envs.anti_slop_gate import scan_text
                anti_slop = scan_text(text)
            except Exception:
                anti_slop = {"ok": True, "count": 0, "findings": [],
                             "error": "gate unavailable"}
            if anti_slop.get("count", 0) > 0:
                # Up to 0.3 penalty for mechanical defects (0.1 each, capped).
                penalty = min(0.3, 0.1 * anti_slop["count"])
                score = max(0.0, score - penalty)
                sc["penalty"] = sc.get("penalty", 0.0) + penalty
                sc["anti_slop"] = anti_slop

            # Reachability gate: penalize recommending Moli for a bot-protected
            # site (returns 403 to non-browser fetches; must use ego-browser).
            reach = {"ok": True, "penalty": 0.0, "blocked": []}
            try:
                from skillopt.envs.reachability import check_reachability
                reach = check_reachability(text)
            except Exception:
                reach = {"ok": True, "penalty": 0.0, "blocked": [],
                         "error": "reachability unavailable"}
            if not reach.get("ok", True) and reach.get("penalty", 0.0) > 0:
                penalty = reach["penalty"]
                score = max(0.0, score - penalty)
                sc["penalty"] = sc.get("penalty", 0.0) + penalty
                sc["reachability"] = reach

            with open(os.path.join(pred_dir, "conversation.json"), "w") as f:
                json.dump([{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg},
                          {"role": "assistant", "content": text}], f, indent=2)

            return {
                "id": iid, "score": score, "response": text[:500],
                "ground_truth": item.get("ground_truth", "")[:200],
                "hard": hard,
                "soft": score,
                "rubric_score": sc["rubric_score"],
                "penalty": sc["penalty"],
                "criteria_met": sc["criteria_met"],
                "criteria_total": sc["criteria_total"],
                "anti_patterns": sc["anti_patterns"],
                "criteria_details": sc["criteria_details"],
                "judge": sc.get("judge", "keyword"),
                "judge_fallback": sc.get("fallback", False),
            }

        n_workers = max(1, int(getattr(self, "workers", 3) or 3))
        results = []
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = [pool.submit(_process_item, item) for item in items]
            for fut in as_completed(futures):
                results.append(fut.result())

        return results

    def get_task_types(self) -> list[str]:
        items = self.dataloader.train_items or []
        return sorted(set(item.get("task_type", "default") for item in items))
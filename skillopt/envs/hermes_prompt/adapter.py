"""Hermes-prompt SkillOpt adapter.

Trains the Hermes Agent stable-tier system prompt as a skill document.
The optimizer edits the skill; this adapter evaluates it by sending
{system=skill, user=question} to the target model and scoring the response
with the hardened score_response() module.
"""
from __future__ import annotations
import json
import os
import urllib.request
from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.envs.hermes_prompt.dataloader import HermesPromptDataLoader
from skillopt.envs.scoring import score_response


# ── TDAI Gateway Integration (shared memory with Prime/DSH) ────────────────
# Mirrors the gebiz adapter: reads shared patterns from TencentDB before
# rollout, writes run outcomes so any agent in the pipeline can discover them.

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


def tdai_read_context(query="hermes system prompt conciseness verification no-hallucination"):
    """Pull shared patterns learned by other agents (Prime/DSH) into the rollout."""
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
    """Log a run outcome so Prime/DSH can discover it.

    Uses the atomic SQLite writer (l1_records + l1_fts) so the write is
    actually indexed by /v2/atomic/search. The /v2/core/write endpoint writes
    to a separate core store that atomic search does NOT index — writing there
    returns 200 but the content is invisible to search (verified 2026-08-18).
    """
    try:
        from skillopt.envs.tdai_atomic_write import write_skillopt_memory
        return write_skillopt_memory(content, "skillopt-hermes-prompt")
    except Exception:
        return False


class HermesPromptAdapter(EnvAdapter):
    # The IMMUTABLE core prompt. Per the Prime/DSH study (see dsh_prime_transfer_pilot),
    # the base system prompt must NOT be edited by the optimizer — behavior improves by
    # tuning a small ADDENDUM (prompt-note) layered on top. `skill_content` is the
    # addendum; `core_baseline.md` is fixed.
    CORE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "skills", "core_baseline.md")

    def __init__(self, split_dir="", data_path="", split_mode="split_dir",
                 split_ratio="2:1:7", split_seed=42, split_output_dir="",
                 workers=4, analyst_workers=4, failure_only=False,
                 minibatch_size=8, edit_budget=4, seed=42, limit=0,
                 max_completion_tokens=4096, **kwargs):
        self.workers = workers
        self.analyst_workers = analyst_workers
        self.failure_only = failure_only
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.max_completion_tokens = int(max_completion_tokens)
        self.reasoning_effort = None
        self.extra_body = None
        self.dataloader = HermesPromptDataLoader(
            split_dir=split_dir, data_path=data_path, split_mode=split_mode,
            split_ratio=split_ratio, split_seed=split_seed,
            split_output_dir=split_output_dir, seed=seed, limit=limit)

    def setup(self, cfg):
        super().setup(cfg)
        self.dataloader.setup(cfg)
        self.reasoning_effort = cfg.get("reasoning_effort")
        self.extra_body = cfg.get("extra_body")

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

    def rollout(self, env_manager, skill_content, out_dir, **kwargs):
        """Roll out the skill on Hermes-style tasks.

        For each item, build {system=skill framing, user=question}, call the
        target model, score with score_response (weighted check/must_not/
        optional/order), persist the trajectory, return id/hard/soft + extras.
        """
        from skillopt.model import chat_target
        items = env_manager
        results = []
        os.makedirs(os.path.join(out_dir, "predictions"), exist_ok=True)

        # Pull shared patterns from TencentDB (Prime/DSH) into the rollout.
        tdai_ctx = tdai_read_context()
        if tdai_ctx:
            print(f"  [TDAI] Loaded {len(tdai_ctx)} chars of shared memory context")

        # ── Prime architecture: immutable core + optimized addendum ─────────
        # The base system prompt (core_baseline.md) is FIXED and never edited.
        # `skill_content` is the small prompt-note/addendum the optimizer tunes.
        # This is the Prime `/refine` pattern: improve behavior via the addendum
        # layer, not by mutating the immutable core (which the conciseness test
        # correctly rejects). The core is loaded once; the addendum is appended.
        try:
            with open(self.CORE_PROMPT_PATH, encoding="utf-8") as _f:
                core_prompt = _f.read().strip()
        except Exception:
            core_prompt = ""
        addendum = (skill_content or "").strip()

        system_msg = (
            "You are a Hermes Agent. Apply the guidance below, then answer the "
            "user's request. Do not include meta-commentary about the guidance.\n\n"
            "--- CORE GUIDANCE (fixed, always applies) ---\n"
            f"{core_prompt}\n"
            "--- END CORE ---"
        )
        if addendum:
            system_msg += (
                "\n\n--- ADDITIONAL GUIDANCE (prompt note) ---\n"
                f"{addendum}\n"
                "--- END ADDITIONAL ---"
            )
        if tdai_ctx:
            system_msg += f"\n\n{tdai_ctx}"

        for item in items:
            iid = item["id"]
            pred_dir = os.path.join(out_dir, "predictions", iid)
            os.makedirs(pred_dir, exist_ok=True)
            user_msg = item["question"]

            try:
                response_text, _usage = chat_target(
                    system=system_msg,
                    user=user_msg,
                    max_completion_tokens=self.max_completion_tokens,
                    reasoning_effort=self.reasoning_effort,
                    extra_body=self.extra_body,
                )
                text = response_text if isinstance(response_text, str) else str(response_text)
            except Exception as e:
                text = f"ERROR: {e}"

            # ── Harden: classify degenerate responses before scoring ────────
            # An empty/None/whitespace response or a model-call ERROR must be
            # surfaced as a distinct failure, not silently scored as a generic
            # "soft below 1.0". This is the difference between "the model gave
            # a wrong answer" (fixable by prompt) and "the harness broke"
            # (fixable by infra) — the optimizer must not conflate them.
            stripped = (text or "").strip()
            if not stripped:
                text = "ERROR: empty response from target model"
            elif stripped.startswith("ERROR:"):
                pass  # already an error marker; scorer handles it
            elif stripped.lower().startswith("error:"):
                text = "ERROR:" + stripped[len("error:"):]

            # Hardened scorer. CRITICAL: read sc["soft"], NOT sc["score"].
            sc = score_response(
                text,
                check=item.get("check"),
                must_not=item.get("must_not"),
                optional=item.get("optional"),
                order=item.get("order"),
                max_chars=item.get("max_chars"),
            )
            hard = sc.get("hard", 0)
            soft = sc.get("soft", 0.0)

            # Sanity guard: hard>0 with soft<=0 is impossible (hard derives
            # from soft) — signals a broken scorer contract.
            if hard > 0 and soft <= 0:
                print(f"    [WARN] {iid}: hard={hard} but soft={soft} — scorer contract broken")

            # ── Telemetry: rich per-item pass/fail signal for the optimizer ──
            # Mirrors the webintel adapter. The trainer's optimizer consumes
            # `fail_reason` (grouped by _extract_failure_patterns) and the
            # analyst reads `criteria_details` to understand WHY an item
            # failed. Without these, the optimizer sees only a hard 0/1 and
            # cannot learn what to fix.
            check_specs = item.get("check") or []
            matched = sc.get("matched", [])
            missed = sc.get("missed", [])
            violations = sc.get("violations", [])
            criteria_details = [
                {
                    "criterion": p.get("pattern", p) if isinstance(p, dict) else p,
                    "met": (p.get("pattern", p) if isinstance(p, dict) else p) in matched,
                }
                for p in check_specs
            ]
            # Build a human-readable fail_reason for the optimizer.
            fail_reason = ""
            if not hard:
                reasons = []
                # Surface harness/infra failures distinctly from wrong answers.
                if stripped.startswith("ERROR:"):
                    reasons.append(f"harness_error: {stripped[len('ERROR:'):].strip()[:120]}")
                elif not stripped:
                    reasons.append("empty_response")
                if missed:
                    reasons.append(f"missing: {', '.join(missed)}")
                if violations:
                    reasons.append(f"forbidden: {', '.join(violations)}")
                # Only report wrong-order when there IS an order constraint AND
                # the response is not an error/empty (the scorer's error branch
                # returns order_score=0.0 spuriously — a false positive).
                has_order = bool(item.get("order"))
                if has_order and not stripped.startswith("ERROR:") and sc.get("order_score", 1.0) < 1.0:
                    reasons.append(f"wrong order (order_score={sc.get('order_score', 0):.2f})")
                if sc.get("length_penalty", 0.0) > 0:
                    reasons.append(f"too long (length_penalty={sc.get('length_penalty', 0):.2f})")
                fail_reason = "; ".join(reasons) if reasons else f"soft={soft:.2f} below 1.0"

            results.append({
                "id": iid,
                "hard": hard,
                "soft": soft,
                "response": text[:500],
                "ground_truth": item.get("ground_truth", "")[:200],
                "task_type": item.get("task_type", ""),
                "matched": matched,
                "missed": missed,
                "violations": violations,
                "fail_reason": fail_reason,
                "criteria_met": len(matched),
                "criteria_total": len(check_specs),
                "criteria_details": criteria_details,
                "order_score": sc.get("order_score", 1.0),
                "length_penalty": sc.get("length_penalty", 0.0),
            })

            with open(os.path.join(pred_dir, "conversation.json"), "w") as f:
                json.dump([
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": text},
                ], f, indent=2)

        # ── Pass/fail telemetry log (JSONL) for post-hoc analysis ──────────
        # One line per item: id, task_type, hard/soft, fail_reason, criteria.
        # This is the raw signal the optimizer and analyst consume to improve
        # the test AND the training. Written to <out_dir>/telemetry.jsonl.
        if results:
            import time as _time
            ts = _time.strftime("%Y-%m-%dT%H:%M:%S")
            telemetry_path = os.path.join(out_dir, "telemetry.jsonl")
            with open(telemetry_path, "a") as f:
                for r in results:
                    f.write(json.dumps({
                        "ts": ts,
                        "id": r["id"],
                        "task_type": r["task_type"],
                        "hard": r["hard"],
                        "soft": r["soft"],
                        "fail_reason": r["fail_reason"],
                        "criteria_met": r["criteria_met"],
                        "criteria_total": r["criteria_total"],
                        "order_score": r["order_score"],
                        "length_penalty": r["length_penalty"],
                    }, ensure_ascii=False) + "\n")

        # Log the batch outcome to TencentDB so Prime/DSH can discover it.
        if results:
            n = len(results)
            hard = sum(1 for r in results if r["hard"])
            soft = sum(r["soft"] for r in results) / n
            # Include the top failure patterns in the shared-memory write so
            # Prime/DSH can see what the hermes-prompt loop is struggling with.
            from collections import Counter
            fail_counts = Counter(
                (r["fail_reason"] or "ok").split(";")[0].strip()
                for r in results if not r["hard"]
            )
            top_fails = ", ".join(
                f"{reason}(x{c})" for reason, c in fail_counts.most_common(3)
            ) or "none"
            wrote = tdai_write_memory(
                f"hermes-prompt rollout: {hard}/{n} hard, soft={soft:.3f} "
                f"(out_dir={out_dir}); top failures: {top_fails}"
            )
            if not wrote:
                print(f"    [WARN] TDAI write failed for {out_dir} — shared memory not updated")

        return results

    def reflect(self, results, skill_content, out_dir, **kwargs):
        """Analyze rollout results and produce patches, ENFORCING no-growth.

        The optimizer model (nemotron-3.5-lightning) ignores the brevity
        constraint in the analyst prompt and emits `append`/`insert_after`
        ops that grow the skill — 5 of 14 steps in the v8 run were wasted
        on growing candidates that the veto then rejected. Prompt-level
        constraint is insufficient; enforce it at the code level here.

        Any edit that would grow the skill (append/insert_after, or a
        replace that lengthens its target) is dropped. If no compliant
        edits remain, the patch is dropped entirely (skill unchanged).
        """
        from skillopt.gradient.reflect import run_minibatch_reflect

        raw = run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=kwargs.get(
                "prediction_dir", os.path.join(out_dir, "predictions")
            ),
            patches_dir=kwargs.get(
                "patches_dir", os.path.join(out_dir, "patches")
            ),
            workers=self.analyst_workers,
            failure_only=self.failure_only,
            minibatch_size=self.minibatch_size,
            edit_budget=self.edit_budget,
            random_seed=kwargs.get("random_seed"),
            error_system=self.get_error_minibatch_prompt(),
            success_system=self.get_success_minibatch_prompt(),
            step_buffer_context=kwargs.get("step_buffer_context", ""),
            meta_skill_context=kwargs.get("meta_skill_context", ""),
            update_mode=getattr(self, "_cfg", {}).get("skill_update_mode", "patch"),
        )

        # ── Code-level no-growth enforcement ─────────────────────────────
        # The skill is a system prompt scored on CONCISENESS. Growth is
        # always rejected by the gate (100+ steps of evidence). Filter out
        # any edit that grows the skill so the optimizer can't waste steps.
        filtered = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            inner = p.get("patch", p)
            if not isinstance(inner, dict):
                continue
            edits = inner.get("edits", [])
            kept = []
            for e in edits:
                if not isinstance(e, dict):
                    continue
                op = e.get("op")
                if op in ("append", "insert_after"):
                    continue  # always grows — drop
                if op == "replace":
                    # A replace that lengthens its target grows the skill.
                    target = e.get("target", "")
                    content = e.get("content", "")
                    if len(str(content)) > len(str(target)):
                        continue
                kept.append(e)
            if not kept:
                continue  # no compliant edits — drop the whole patch
            inner = dict(inner)
            inner["edits"] = kept
            filtered.append({**p, "patch": inner})

        return filtered

    def get_task_types(self) -> list[str]:
        items = self.dataloader.train_items or []
        return sorted(set(item.get("task_type", "default") for item in items))

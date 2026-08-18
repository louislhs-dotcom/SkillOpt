"""GeBIZ procurement search environment adapter for SkillOpt.

Optimizes the GeBIZ search skill (SKILL.md) so agents correctly search
Singapore's GeBIZ e-procurement portal. The key challenge: GeBIZ is a JSF
(JavaServer Faces) app — plain GET returns an empty shell ("No opportunity
found"); results require a full form POST with a valid javax.faces.ViewState.

The skill is evaluated by asking the target model how to search GeBIZ and
scoring whether it produces the correct JSF postback approach (endpoint,
ViewState, POST fields) rather than a naive curl GET.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.envs.gebiz.dataloader import GebizDataLoader
from skillopt.envs.gebiz.scoring import score_item
from skillopt.envs.gebiz.rubric_scoring import score_with_rubric, GEBIZ_RUBRIC


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


def tdai_read_context(query="gebiz procurement search JSF postback ViewState"):
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
        _tdai_post("/v2/core/write", {"content": content, "type": "skillopt-gebiz"})
        return True
    except Exception:
        return False


def tdai_search(query, limit=5):
    try:
        result = _tdai_post("/v2/atomic/search", {"query": query, "limit": limit})
        return result.get("data", {}).get("items", [])
    except Exception:
        return []


class GebizAdapter(EnvAdapter):
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
        self.dataloader = GebizDataLoader(
            split_dir=split_dir, data_path=data_path, split_mode=split_mode,
            split_ratio=split_ratio, split_seed=split_seed,
            split_output_dir=split_output_dir, seed=seed, limit=limit)
        self._tdai_cache = None

    def setup(self, cfg):
        super().setup(cfg)
        self.dataloader.setup(cfg)
        # reasoning_effort and extra_body from config (for Ollama Cloud / NIM)
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

    def _get_tdai_context(self):
        if self._tdai_cache is None:
            self._tdai_cache = tdai_read_context()
            if self._tdai_cache:
                print(f"  [TDAI] Loaded {len(self._tdai_cache)} chars of shared memory context")
        return self._tdai_cache

    def rollout(self, env_manager, skill_content, out_dir, **kwargs):
        """Roll out the skill on GeBIZ search tasks.

        For each task, the target model produces a GeBIZ search approach
        (command / script / explanation) based on the skill. We score by
        whether it includes the required patterns: the correct endpoint,
        the JSF ViewState requirement, and the POST (not GET) approach.
        """
        from skillopt.model import chat_target
        items = env_manager
        results = []
        os.makedirs(os.path.join(out_dir, "predictions"), exist_ok=True)

        tdai_ctx = self._get_tdai_context()
        if tdai_ctx:
            system_msg = (
                f"You are an agent that searches Singapore's GeBIZ e-procurement portal "
                f"(https://www.gebiz.gov.sg). Follow the skill guidelines to produce the "
                f"correct search approach. GeBIZ is a JSF app: results require a form POST "
                f"with a valid javax.faces.ViewState, not a plain GET.\n\n"
                f"SKILL:\n{skill_content}\n\n"
                f"{tdai_ctx}"
            )
        else:
            system_msg = (
                f"You are an agent that searches Singapore's GeBIZ e-procurement portal "
                f"(https://www.gebiz.gov.sg). Follow the skill guidelines to produce the "
                f"correct search approach. GeBIZ is a JSF app: results require a form POST "
                f"with a valid javax.faces.ViewState, not a plain GET.\n\n"
                f"SKILL:\n{skill_content}"
            )

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

            # Granular rubric scoring (replaces binary hard/soft)
            sc = score_with_rubric(text, GEBIZ_RUBRIC)
            score = sc.get("score", 0.0)
            hard = sc.get("hard", 1.0 if score >= 0.9 else 0.0)

            results.append({
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
            })

            with open(os.path.join(pred_dir, "conversation.json"), "w") as f:
                json.dump([{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg},
                          {"role": "assistant", "content": text}], f, indent=2)

        return results

    def get_task_types(self) -> list[str]:
        items = self.dataloader.train_items or []
        return sorted(set(item.get("task_type", "default") for item in items))

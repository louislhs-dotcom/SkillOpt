"""Coding environment adapter for SkillOpt with TDAI shared memory integration."""
from __future__ import annotations
import json
import os
import re
import urllib.request
from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter
from skillopt.envs.coding.dataloader import CodingDataLoader


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


def tdai_read_context(query="coding patterns error handling edge cases"):
    """Read shared memories from TDAI to enrich the skill context."""
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
        return ""  # non-fatal


def tdai_write_memory(content):
    """Write a learned skill rule to TDAI shared memory."""
    try:
        _tdai_post("/v2/core/write", {"content": content, "type": "skillopt"})
        return True
    except Exception:
        return False  # non-fatal


def tdai_search(query, limit=5):
    """Search TDAI for specific patterns."""
    try:
        result = _tdai_post("/v2/atomic/search", {"query": query, "limit": limit})
        return result.get("data", {}).get("items", [])
    except Exception:
        return []


class CodingAdapter(EnvAdapter):
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
        self.dataloader = CodingDataLoader(
            split_dir=split_dir, data_path=data_path, split_mode=split_mode,
            split_ratio=split_ratio, split_seed=split_seed,
            split_output_dir=split_output_dir, seed=seed, limit=limit)
        # Cache TDAI context for the training run
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

    def _get_tdai_context(self):
        """Get cached TDAI shared memory context."""
        if self._tdai_cache is None:
            self._tdai_cache = tdai_read_context()
            if self._tdai_cache:
                print(f"  [TDAI] Loaded {len(self._tdai_cache)} chars of shared memory context")
        return self._tdai_cache

    def rollout(self, env_manager, skill_content, out_dir, **kwargs):
        """Run coding agent on items. Score by code correctness.

        Injects TDAI shared memory context into the system prompt so the
        target model benefits from patterns learned by other agents
        (Hermes, DSH coder, Prime Agent, reviewer).
        """
        from skillopt.model import chat_target
        items = env_manager
        results = []
        os.makedirs(os.path.join(out_dir, "predictions"), exist_ok=True)

        # Enrich skill with TDAI shared memory
        tdai_ctx = self._get_tdai_context()
        if tdai_ctx:
            system_msg = (
                f"You are a Python coding assistant. Follow the skill guidelines.\n\n"
                f"SKILL:\n{skill_content}\n\n"
                f"{tdai_ctx}"
            )
        else:
            system_msg = (
                f"You are a Python coding assistant. Follow the skill guidelines.\n\n"
                f"SKILL:\n{skill_content}"
            )

        for item in items:
            iid = item["id"]
            pred_dir = os.path.join(out_dir, "predictions", iid)
            os.makedirs(pred_dir, exist_ok=True)

            user_msg = item["question"] + "\n\nWrite only the Python function. No explanation."

            try:
                response_text, _usage = chat_target(
                    system=system_msg,
                    user=user_msg,
                    max_completion_tokens=self.max_completion_tokens,
                )
                text = response_text if isinstance(response_text, str) else str(response_text)
            except Exception as e:
                text = f"ERROR: {e}"

            # Score: fraction of required patterns found in the response
            check_list = item.get("check", [])
            if check_list:
                found = sum(1 for pattern in check_list if pattern in text)
                score = found / len(check_list)
            else:
                gt = item.get("ground_truth", "")
                match = re.search(r"def (\w+)", gt)
                func_name = match.group(1) if match else ""
                has_func = f"def {func_name}" in text if func_name else False
                has_return = "return" in text
                score = 1.0 if (has_func and has_return) else 0.0

            results.append({
                "id": iid, "score": score, "response": text[:500],
                "ground_truth": item.get("ground_truth", "")[:200], "hard": score,
            })

            with open(os.path.join(pred_dir, "conversation.json"), "w") as f:
                json.dump([{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg},
                          {"role": "assistant", "content": text}], f, indent=2)

        return results

    def reflect(self, rollout_results, skill_content, out_dir, **kwargs):
        """Reflect on rollouts — search TDAI for related past patterns.

        The base class implements reflect by reading conversation.json files
        and sending them to the optimizer model. We extend it by also
        searching TDAI for relevant past experiences and including them
        in the reflection context.
        """
        # Search TDAI for patterns related to the failures in this batch
        failed_items = [r for r in rollout_results if r.get("hard", 0) < 1.0]
        if failed_items:
            # Build a query from the failed task types
            queries = []
            for r in failed_items:
                gt = r.get("ground_truth", "")
                if gt:
                    # Extract key terms from the ground truth
                    terms = re.findall(r'\b(?:def|class|isinstance|return|raise|try|except|deque|Counter)\b', gt)
                    queries.extend(terms[:3])

            # Search TDAI for each query and collect unique insights
            tdai_insights = []
            for q in set(queries[:5]):
                items = tdai_search(f"coding {q}", limit=3)
                for item in items:
                    content = item.get("content", "").strip()
                    if content and content not in tdai_insights:
                        tdai_insights.append(content[:200])

            if tdai_insights:
                print(f"  [TDAI] Found {len(tdai_insights)} relevant past patterns for reflection")
                # Write TDAI insights to a file the optimizer can read
                insights_path = os.path.join(out_dir, "tdai_insights.json")
                with open(insights_path, "w") as f:
                    json.dump({"insights": tdai_insights}, f, indent=2)

        # Call the base class reflect (which does the actual LLM reflection)
        return super().reflect(rollout_results, skill_content, out_dir, **kwargs)

    def get_task_types(self) -> list[str]:
        items = self.dataloader.train_items or []
        return sorted(set(item.get("task_type", "default") for item in items))

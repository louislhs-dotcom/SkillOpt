"""Coding task dataloader."""
from __future__ import annotations
import json
from pathlib import Path
from skillopt.datasets.base import SplitDataLoader


def _normalize_item(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or ""),
        "question": str(raw.get("question") or raw.get("prompt") or ""),
        "ground_truth": str(raw.get("ground_truth") or raw.get("answer") or ""),
        "task_type": str(raw.get("task_type") or "notebooklm"),
        "check": list(raw.get("check") or []),
        "order": list(raw.get("order") or []),
        "must_not": list(raw.get("must_not") or []),
        "optional": list(raw.get("optional") or []),
    }


class NotebookLMDataLoader(SplitDataLoader):
    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        json_files = sorted(path.glob("*.json"))
        if json_files:
            with json_files[0].open(encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                return [_normalize_item(row) for row in payload]
        return []

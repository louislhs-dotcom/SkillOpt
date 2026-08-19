"""Web Intelligence task dataloader with template + site-config support."""
from __future__ import annotations
import json
from pathlib import Path
from skillopt.datasets.base import SplitDataLoader


def _normalize_item(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or ""),
        "question": str(raw.get("question") or raw.get("prompt") or ""),
        "ground_truth": str(raw.get("ground_truth") or raw.get("answer") or ""),
        "task_type": str(raw.get("task_type") or "webintel"),
        "site": str(raw.get("site") or ""),
        "check": list(raw.get("check") or []),
        "order": list(raw.get("order") or []),
        "must_not": list(raw.get("must_not") or []),
        "optional": list(raw.get("optional") or []),
    }


def load_skill_template(template_path: str) -> str:
    """Load the general template skill."""
    with open(template_path, encoding="utf-8") as f:
        return f.read()


def load_site_config(site_config_path: str) -> str:
    """Load a site-specific configuration."""
    with open(site_config_path, encoding="utf-8") as f:
        return f.read()


def merge_skill(template: str, site_config: str | None) -> str:
    """Merge template with optional site config."""
    if not site_config:
        return template
    return f"{template}\n\n---\n\n# Site-Specific Configuration\n\n{site_config}"


class WebIntelDataLoader(SplitDataLoader):
    def __init__(self, split_dir="", data_path="", split_mode="split_dir",
                 split_ratio="2:1:7", split_seed=42, split_output_dir="",
                 seed=42, limit=0, skill_template_path="",
                 site_config_path="", **kwargs):
        self.skill_template_path = skill_template_path
        self.site_config_path = site_config_path
        self._merged_skill = None
        self._site_config = None
        super().__init__(
            split_dir=split_dir, data_path=data_path, split_mode=split_mode,
            split_ratio=split_ratio, split_seed=split_seed,
            split_output_dir=split_output_dir, seed=seed, limit=limit)

    def setup(self, cfg):
        super().setup(cfg)
        # Config is already flattened - use flat keys
        template_path = cfg.get("skill_template", "") or cfg.get("env.skill_template", "")
        site_config_path = cfg.get("site_config", "") or cfg.get("env.site_config", "")
        
        if template_path:
            template = load_skill_template(template_path)
        else:
            template = ""
        site_config = load_site_config(site_config_path) if site_config_path else None
        self._site_config = site_config
        self._merged_skill = merge_skill(template, site_config)

    def get_merged_skill(self) -> str:
        """Return the combined template + site config skill."""
        return self._merged_skill or ""

    def get_site_config(self) -> str:
        """Return the site-specific configuration alone (no template)."""
        return self._site_config or ""

    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        json_files = sorted(path.glob("*.json"))
        if json_files:
            with json_files[0].open(encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                return [_normalize_item(row) for row in payload]
        return []
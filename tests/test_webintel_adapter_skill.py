"""Regression tests: the optimized skill must reach the target model.

``WebIntelAdapter.rollout`` used to build its system prompt from
``self.get_merged_skill() or skill_content``. The dataloader's cached
``template + site_config`` merge is always truthy, so the ``or`` fallback never
fired and the optimizer's edits to ``skill_content`` were silently discarded —
every WebIntel run was a null experiment (all ``skill_v000*.md`` byte-identical).

These tests pin the fixed contract: ``skill_content`` is the BASE of the system
prompt and the site config is appended to it.
"""
from __future__ import annotations

from skillopt.envs.webintel.adapter import WebIntelAdapter
from skillopt.envs.webintel.dataloader import merge_skill

TEMPLATE = "# Fixed Template\nGeneric routing rules that must NOT override the skill."
SITE_CONFIG = "# Carousell\nUse ego-browser for carousell.sg."
SKILL = "# OPTIMIZED SKILL v7\nUNIQUE_OPTIMIZER_EDIT_MARKER: prefer defuddle for articles."


def _adapter() -> WebIntelAdapter:
    """Adapter with the dataloader's merge state injected (no disk / no cfg)."""
    ad = WebIntelAdapter()
    ad.dataloader._merged_skill = merge_skill(TEMPLATE, SITE_CONFIG)
    ad.dataloader._site_config = SITE_CONFIG
    ad._tdai_cache = ""  # skip the TDAI gateway call
    return ad


def test_get_merged_skill_uses_optimized_content_as_base():
    merged = _adapter().get_merged_skill(SKILL)
    assert "UNIQUE_OPTIMIZER_EDIT_MARKER" in merged
    assert SITE_CONFIG in merged
    assert "# Fixed Template" not in merged


def test_get_merged_skill_falls_back_to_template_when_empty():
    ad = _adapter()
    assert ad.get_merged_skill("") == merge_skill(TEMPLATE, SITE_CONFIG)
    assert ad.get_merged_skill("   ") == merge_skill(TEMPLATE, SITE_CONFIG)


def test_dataloader_site_config_accessor_excludes_template():
    ad = _adapter()
    assert ad.dataloader.get_site_config() == SITE_CONFIG
    assert "# Fixed Template" not in ad.dataloader.get_site_config()


def test_rollout_system_prompt_contains_optimized_skill(tmp_path, monkeypatch):
    """The prompt actually sent to the target must carry the optimizer's edits."""
    import skillopt.model as model

    captured = {}

    def fake_chat_target(system, user, **kwargs):
        captured["system"] = system
        return "Use defuddle parse --markdown for the article.", {}

    monkeypatch.setattr(model, "chat_target", fake_chat_target)

    items = [{
        "id": "t1",
        "question": "How do I extract a news article?",
        "task_type": "webintel",
        "site": "",
        "check": ["defuddle"],
        "must_not": [],
        "optional": [],
    }]
    results = _adapter().rollout(items, SKILL, str(tmp_path))

    assert len(results) == 1
    system = captured["system"]
    assert "UNIQUE_OPTIMIZER_EDIT_MARKER" in system
    assert "Use ego-browser for carousell.sg." in system
    assert "Generic routing rules that must NOT override the skill." not in system


def test_rollout_prompt_changes_when_skill_changes(tmp_path, monkeypatch):
    """Two different skills must produce two different system prompts."""
    import skillopt.model as model

    seen = []
    monkeypatch.setattr(
        model, "chat_target",
        lambda system, user, **kw: (seen.append(system), ("ok", {}))[1],
    )

    items = [{"id": "t1", "question": "q", "task_type": "webintel",
              "site": "", "check": ["ok"], "must_not": [], "optional": []}]
    ad = _adapter()
    ad.rollout(items, "# SKILL A\nalpha marker", str(tmp_path / "a"))
    ad.rollout(items, "# SKILL B\nbravo marker", str(tmp_path / "b"))

    assert seen[0] != seen[1]
    assert "alpha marker" in seen[0] and "alpha marker" not in seen[1]
    assert "bravo marker" in seen[1]

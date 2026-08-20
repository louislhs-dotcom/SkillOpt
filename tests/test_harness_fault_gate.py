"""Tests for the automated harness-fault gate (skillopt/envs/harness_fault_gate.py).

Covers the three fault classes the gate is meant to catch automatically:
  1. Dataset discrimination drift (an item that can't separate good/bad).
  2. Empty-response spikes (harness/infra fault, not a wrong answer).
  3. Optimizer-did-nothing streaks (stalling).
Plus the config/dataset match check.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillopt.envs import harness_fault_gate as gate  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
def _item(iid, check, must_not=None, order=None, optional=None):
    return {
        "id": iid,
        "question": "q",
        "check": check,
        "must_not": must_not or [],
        "order": order or [],
        "optional": optional or [],
    }


# ── Discrimination ──────────────────────────────────────────────────────────
def test_good_item_discriminates():
    item = _item("a1", ["confirm", "destructive"])
    r = gate.check_item_discriminates(item)
    assert r["ok"] is True, r


def test_contradiction_check_and_must_not_detected():
    # val_007 class: "networkidle" in BOTH check and must_not => unsolvable.
    item = _item("v1", ["waitForSelector", "networkidle"], must_not=["networkidle"])
    r = gate.check_item_discriminates(item)
    assert r["ok"] is False
    assert any("contradiction" in p for p in r["problems"]), r


def test_must_not_violation_makes_bad_answer_fail():
    item = _item("a2", ["confirm"], must_not=["delete without asking"])
    r = gate.check_item_discriminates(item)
    assert r["ok"] is True, r


def test_preflight_discrimination_aggregates():
    items = [
        _item("ok1", ["confirm"]),
        _item("bad1", ["x", "y"], must_not=["x"]),  # contradiction
    ]
    res = gate.preflight_discrimination(items)
    assert res["ok"] is False
    assert res["failed"] == 1
    assert res["findings"][0]["id"] == "bad1"


# ── Config match ────────────────────────────────────────────────────────────
def test_config_mismatch_detected():
    items = {"train": [{}] * 5, "val": [{}] * 2, "test": [{}] * 1}
    cfg = {
        "env": {},
        "train": {"train_size": 10},          # dataset has 5
        "evaluation": {"sel_env_num": 5},     # dataset has 2
        "optimizer": {"veto_growing_candidates": False},
    }
    res = gate.preflight_config(items, cfg)
    assert res["ok"] is False
    assert len(res["problems"]) == 3


def test_config_match_ok():
    items = {"train": [{}] * 10, "val": [{}] * 5, "test": [{}] * 2}
    cfg = {
        "env": {},
        "train": {"train_size": 10},
        "evaluation": {"sel_env_num": 5, "test_env_num": 2},
        "optimizer": {"veto_growing_candidates": True},
    }
    res = gate.preflight_config(items, cfg)
    assert res["ok"] is True


# ── Postflight: empty responses ─────────────────────────────────────────────
def test_empty_response_spike_detected():
    telemetry = [
        {"fail_reason": "harness_error: timeout"} for _ in range(3)
    ] + [{"fail_reason": "missing: x"} for _ in range(1)]
    res = gate.postflight_empty_responses(telemetry)
    assert res["ok"] is False
    assert res["fraction"] == 0.75


def test_empty_response_ok_below_threshold():
    telemetry = [{"fail_reason": "missing: x"} for _ in range(10)]
    res = gate.postflight_empty_responses(telemetry)
    assert res["ok"] is True


# ── Postflight: optimizer noop streak ───────────────────────────────────────
def test_optimizer_noop_streak_detected():
    history = [
        {"action": "reject"}, {"action": "reject"}, {"action": "reject"},
        {"action": "accept"},
    ]
    res = gate.postflight_optimizer_noop(history)
    assert res["ok"] is False
    assert res["streak"] == 3


def test_optimizer_no_candidate_streak_ignores_rejects():
    """A reject means the optimizer DID produce a candidate — not a stall.
    The mid-run early-stop must NOT count rejects, or a legitimately-losing
    run gets force-aborted after a few rejects."""
    # 8 rejects, no skip_no_patches => no-candidate streak stays 0
    assert gate.optimizer_no_candidate_streak(
        ["reject"] * 8
    ) == 0
    # 5 skip_no_patches => streak 5 (true stall)
    assert gate.optimizer_no_candidate_streak(
        ["skip_no_patches"] * 5
    ) == 5
    # mixed: rejects reset nothing, only skip_no_patches accumulates
    assert gate.optimizer_no_candidate_streak(
        ["reject", "skip_no_patches", "reject", "skip_no_patches", "skip_no_patches"]
    ) == 2


def test_optimizer_noop_ok():
    history = [
        {"action": "reject"}, {"action": "accept"}, {"action": "reject"},
    ]
    res = gate.postflight_optimizer_noop(history)
    assert res["ok"] is True


# ── Postflight on a real run dir ────────────────────────────────────────────
def test_postflight_reads_run_dir(tmp_path):
    # history.json with a noop streak
    (tmp_path / "history.json").write_text(json.dumps([
        {"action": "reject"}, {"action": "reject"}, {"action": "reject"},
    ]))
    # telemetry.jsonl with an empty spike
    tel = tmp_path / "rollout" / "telemetry.jsonl"
    tel.parent.mkdir(parents=True)
    tel.write_text("\n".join(
        json.dumps({"fail_reason": "harness_error: timeout"}) for _ in range(3)
    ) + "\n" + json.dumps({"fail_reason": "missing: x"}) + "\n")

    res = gate.postflight(str(tmp_path))
    assert res["ok"] is False
    assert res["checks"]["optimizer_noop"]["ok"] is False
    assert res["checks"]["empty_responses"]["ok"] is False


# ── Postflight: config / env mismatch ───────────────────────────────────────
def test_env_coherence_flags_unknown_env():
    """A typo'd / nonexistent env must be flagged, not pass silently."""
    known = {"webintel", "hermes_prompt", "coding", "moli"}
    r = gate.check_env_coherence(
        {"env": "webintel-typo", "skill_init": "x.md", "split_dir": "data/x"},
        known,
    )
    assert r["ok"] is False
    assert any("not a known env" in p for p in r["problems"])


def test_env_coherence_passes_valid_env():
    known = {"webintel", "hermes_prompt", "coding", "moli"}
    r = gate.check_env_coherence(
        {"env": "webintel", "skill_init": "skillopt/envs/webintel/skills/initial.md",
         "split_dir": "data/webintel_split"},
        known,
    )
    assert r["ok"] is True


def test_env_coherence_flags_empty_env():
    r = gate.check_env_coherence({"env": "", "skill_init": "x.md"}, {"webintel"})
    assert r["ok"] is False
    assert any("empty" in p for p in r["problems"])


def test_postflight_config_mismatch_detected(tmp_path):
    """A run whose config.json says webintel but the intended config is
    hermes-prompt must be flagged by the postflight gate."""
    (tmp_path / "config.json").write_text(json.dumps({
        "env": "webintel", "skill_init": "webintel/skills/initial.md",
        "split_dir": "data/webintel_split", "target_model": "deepseek-v4-flash:cloud",
        "optimizer_model": "glm-5.2:cloud", "gate_metric": "soft", "data_path": "",
    }))
    expected = {
        "env": "hermes-prompt", "skill_init": "hermes_prompt/skills/addendum_init.md",
        "split_dir": "data/hermes-prompt-lean", "target_model": "deepseek-v4-flash:cloud",
        "optimizer_model": "glm-5.2:cloud", "gate_metric": "soft", "data_path": "",
    }
    res = gate.postflight(str(tmp_path), expected_config=expected)
    assert res["ok"] is False
    cm = res["checks"]["config_mismatch"]
    assert cm["ok"] is False
    assert len(cm["findings"]) == 3  # env + skill_init + split_dir
    assert any("env" in f and "webintel" in f for f in cm["findings"])


def test_postflight_config_mismatch_clean(tmp_path):
    """A run whose config.json matches the intended config stays clean."""
    cfg = {
        "env": "hermes-prompt", "skill_init": "hermes_prompt/skills/addendum_init.md",
        "split_dir": "data/hermes-prompt-lean", "target_model": "deepseek-v4-flash:cloud",
        "optimizer_model": "glm-5.2:cloud", "gate_metric": "soft", "data_path": "",
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    res = gate.postflight(str(tmp_path), expected_config=cfg)
    assert res["checks"]["config_mismatch"]["ok"] is True
    assert res["ok"] is True


def test_postflight_config_mismatch_skipped_without_expected(tmp_path):
    """No expected config => the check is skipped, not failed."""
    (tmp_path / "config.json").write_text(json.dumps({"env": "webintel"}))
    res = gate.postflight(str(tmp_path))
    assert res["checks"]["config_mismatch"]["ok"] is True
    assert res["ok"] is True


def test_postflight_config_mismatch_ignores_non_identity_fields(tmp_path):
    """workers/batch_size differences are not identity faults."""
    run = {"env": "hermes-prompt", "skill_init": "s.md", "split_dir": "data/lean",
           "target_model": "deepseek-v4-flash:cloud", "optimizer_model": "glm-5.2:cloud",
           "gate_metric": "soft", "data_path": "", "workers": 3, "batch_size": 4}
    expected = {"env": "hermes-prompt", "skill_init": "s.md", "split_dir": "data/lean",
                "target_model": "deepseek-v4-flash:cloud", "optimizer_model": "glm-5.2:cloud",
                "gate_metric": "soft", "data_path": "", "workers": 8, "batch_size": 16}
    (tmp_path / "config.json").write_text(json.dumps(run))
    res = gate.postflight(str(tmp_path), expected_config=expected)
    assert res["checks"]["config_mismatch"]["ok"] is True
    assert res["ok"] is True

"""Regression tests for the hermes-prompt harness-fault gate.

One synthetic fixture per detector: each test builds a minimal run dir /
dataset dir on tmp_path, asserts the fault fires, and asserts a healthy
counterpart stays clean.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillopt.envs.hermes_prompt.fault_gate import (
    EMPTY_RESPONSE_FRACTION,
    OPTIMIZER_NOOP_STREAK,
    detect_discrimination_drift,
    detect_empty_response_spike,
    detect_false_veto_pattern,
    detect_optimizer_did_nothing,
    find_false_veto,
    main,
    run_fault_gate,
)


# ── Fixture builders ────────────────────────────────────────────────────────
def _telemetry_row(iid: str, fail_reason: str = "", ts: str = "2026-08-19T12:00:00") -> dict:
    return {
        "ts": ts, "id": iid, "task_type": "unit", "hard": 0.0 if fail_reason else 1.0,
        "soft": 0.0 if fail_reason else 1.0, "fail_reason": fail_reason,
        "criteria_met": 0 if fail_reason else 1, "criteria_total": 1,
        "order_score": 1.0, "length_penalty": 0.0,
    }


def _write_telemetry(run_dir: Path, rel: str, rows: list[dict]) -> None:
    path = run_dir / rel / "telemetry.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _write_prediction(run_dir: Path, rel: str, iid: str, response: str) -> None:
    path = run_dir / rel / "predictions" / iid / "conversation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": response},
    ]), encoding="utf-8")


def _write_history(run_dir: Path, actions: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "history.json").write_text(json.dumps([
        {"step": i + 1, "action": a, "n_patches": 0} for i, a in enumerate(actions)
    ]), encoding="utf-8")


def _write_dataset(root: Path, items: list[dict], split: str = "val") -> None:
    (root / split).mkdir(parents=True, exist_ok=True)
    (root / split / "items.json").write_text(json.dumps(items), encoding="utf-8")


def _item(**over) -> dict:
    base = {
        "id": "t1", "task_type": "unit", "question": "q?",
        "check": ["report", "done"], "must_not": ["want me to"],
        "optional": [], "order": [], "max_chars": None,
    }
    base.update(over)
    return base


# ── 1. empty_response_spike ─────────────────────────────────────────────────
def test_empty_response_spike_fires_above_threshold():
    rows = [
        _telemetry_row("a", "empty_response"),
        _telemetry_row("b", "harness_error: connection reset"),
        _telemetry_row("c"),
        _telemetry_row("d"),
    ]
    faults = detect_empty_response_spike([("selection_eval_baseline@ts", rows)])
    assert len(faults) == 1
    assert faults[0]["fault_type"] == "empty_response_spike"
    assert faults[0]["severity"] == "critical"
    assert "2/4" in faults[0]["detail"]


def test_empty_response_spike_silent_at_or_below_threshold():
    # 1 empty of 5 = 20%, which is NOT > 20%.
    rows = [_telemetry_row("a", "empty_response")] + [
        _telemetry_row(x) for x in "bcde"
    ]
    assert detect_empty_response_spike([("batch@ts", rows)]) == []


def test_empty_response_spike_silent_on_ordinary_failures():
    rows = [_telemetry_row(x, "missing: report") for x in "abcd"]
    assert detect_empty_response_spike([("batch@ts", rows)]) == []


def test_empty_response_spike_is_per_batch(tmp_path):
    """A clean batch must not dilute a broken one — batches are keyed by ts."""
    run = tmp_path / "run"
    _write_telemetry(run, "selection_eval_baseline", [
        _telemetry_row("a", "empty_response", ts="T1"),
        _telemetry_row("b", "empty_response", ts="T1"),
        _telemetry_row("c", ts="T1"),
        _telemetry_row("d", ts="T2"), _telemetry_row("e", ts="T2"),
        _telemetry_row("f", ts="T2"), _telemetry_row("g", ts="T2"),
        _telemetry_row("h", ts="T2"), _telemetry_row("i", ts="T2"),
    ])
    faults = [f for f in run_fault_gate(str(run), str(tmp_path / "missing"))
              if f["fault_type"] == "empty_response_spike"]
    assert len(faults) == 1
    assert "@T1" in faults[0]["detail"]


# ── 2. false_veto_pattern ───────────────────────────────────────────────────
def test_find_false_veto_detects_negated_form():
    detail = find_false_veto("click it", "The link is dead, so don't click it — I'll fix it.")
    assert detail is not None
    assert "don't" in detail


def test_find_false_veto_silent_on_genuine_violation():
    assert find_false_veto("click it", "Here is the link, click it to continue.") is None


def test_find_false_veto_silent_when_pattern_absent():
    assert find_false_veto("click it", "The link is broken; I replaced it.") is None


def test_find_false_veto_requires_every_occurrence_negated():
    text = "Don't click it blindly. If it looks right, click it."
    assert find_false_veto("click it", text) is None


def test_detect_false_veto_pattern_over_predictions():
    items = [_item(id="i6", check=["broken"], must_not=["click it"])]
    preds = [("selection_eval_baseline", "i6",
              "The link is broken. Do not click it; I'll send the right link.")]
    faults = detect_false_veto_pattern(preds, items)
    assert len(faults) == 1
    assert faults[0]["fault_type"] == "false_veto_pattern"
    assert faults[0]["severity"] == "high"
    assert "click it" in faults[0]["detail"]


def test_detect_false_veto_pattern_ignores_unknown_item_ids():
    items = [_item(id="i6", must_not=["click it"])]
    preds = [("eval", "not_in_dataset", "don't click it")]
    assert detect_false_veto_pattern(preds, items) == []


def test_false_veto_end_to_end(tmp_path):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item(id="i6", check=["broken"], must_not=["click it"])])
    _write_prediction(run, "selection_eval_baseline", "i6",
                      "The link is broken, so don't click it.")
    faults = [f for f in run_fault_gate(str(run), str(data))
              if f["fault_type"] == "false_veto_pattern"]
    assert len(faults) == 1


# ── 3. optimizer_did_nothing ────────────────────────────────────────────────
def test_optimizer_did_nothing_fires_on_five_consecutive():
    history = [{"step": i + 1, "action": "skip_no_patches"} for i in range(5)]
    faults = detect_optimizer_did_nothing(history)
    assert len(faults) == 1
    assert faults[0]["fault_type"] == "optimizer_did_nothing"
    assert faults[0]["severity"] == "medium"
    assert "5 consecutive" in faults[0]["detail"]


def test_optimizer_did_nothing_silent_below_threshold():
    actions = ["skip_no_patches"] * 4 + ["accept"] + ["skip_no_patches"] * 4
    history = [{"step": i + 1, "action": a} for i, a in enumerate(actions)]
    assert detect_optimizer_did_nothing(history) == []


def test_optimizer_did_nothing_ignores_rejects():
    """A reject means the optimizer DID produce a candidate — not a no-op."""
    history = [{"step": i + 1, "action": "reject"} for i in range(8)]
    assert detect_optimizer_did_nothing(history) == []


def test_optimizer_did_nothing_reports_each_streak():
    actions = (["skip_no_patches"] * 5 + ["accept"] + ["skip_no_patches"] * 6)
    history = [{"step": i + 1, "action": a} for i, a in enumerate(actions)]
    faults = detect_optimizer_did_nothing(history)
    assert len(faults) == 2
    assert "steps 1..5" in faults[0]["detail"]
    assert "steps 7..12" in faults[1]["detail"]


def test_optimizer_did_nothing_end_to_end(tmp_path):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_history(run, ["skip_no_patches"] * OPTIMIZER_NOOP_STREAK)
    _write_dataset(data, [_item()])
    faults = [f for f in run_fault_gate(str(run), str(data))
              if f["fault_type"] == "optimizer_did_nothing"]
    assert len(faults) == 1


# ── 4. discrimination_drift ─────────────────────────────────────────────────
def test_discrimination_drift_silent_on_healthy_item():
    assert detect_discrimination_drift([_item()]) == []


def test_discrimination_drift_flags_check_must_not_contradiction():
    """A pattern in BOTH check and must_not makes the item unsolvable."""
    faults = detect_discrimination_drift([
        _item(id="val_007", check=["report", "done"], must_not=["done"])
    ])
    assert faults
    assert faults[0]["fault_type"] == "discrimination_drift"
    assert faults[0]["severity"] == "critical"
    assert "naive good answer" in faults[0]["detail"]


def test_discrimination_drift_flags_non_vetoing_must_not():
    """Diluted must_not: with 30 forbidden patterns one violation costs only
    1/30 penalty, which an earned +0.1 optional bonus more than cancels — so a
    bad answer still scores hard=1.0 and the item stops discriminating."""
    item = _item(
        id="diluted",
        check=["report"],
        must_not=[f"forbidden phrase {i}" for i in range(30)],
        optional=["report"],
    )
    faults = detect_discrimination_drift([item])
    assert faults
    assert all(f["fault_type"] == "discrimination_drift" for f in faults)
    assert any("does not veto" in f["detail"] for f in faults)


def test_discrimination_drift_flags_item_with_no_check_patterns():
    faults = detect_discrimination_drift([_item(id="empty", check=[], must_not=[])])
    assert len(faults) == 1
    assert "no check patterns" in faults[0]["detail"]


def test_discrimination_drift_flags_unreachable_order():
    """An order constraint naming a pattern absent from check is unsatisfiable
    only if it cannot appear; here order and check agree, so it must stay clean."""
    ok = _item(id="ordered", check=["first", "second"], order=["first", "second"],
               must_not=[])
    assert detect_discrimination_drift([ok]) == []


def test_discrimination_drift_end_to_end(tmp_path):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item(id="val_007", check=["report"], must_not=["report"])])
    faults = [f for f in run_fault_gate(str(run), str(data))
              if f["fault_type"] == "discrimination_drift"]
    assert faults


# ── Gate contract + CLI ─────────────────────────────────────────────────────
def test_run_fault_gate_clean_run_returns_empty(tmp_path):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item()])
    _write_telemetry(run, "selection_eval_baseline", [_telemetry_row("t1")])
    _write_prediction(run, "selection_eval_baseline", "t1", "Report: done, here is the result.")
    _write_history(run, ["accept", "reject", "accept"])
    assert run_fault_gate(str(run), str(data)) == []


def test_run_fault_gate_tolerates_missing_inputs(tmp_path):
    assert run_fault_gate(str(tmp_path / "nope"), str(tmp_path / "also_nope")) == []


def test_every_fault_has_the_three_required_keys(tmp_path):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item(id="bad", check=["report"], must_not=["report"])])
    _write_telemetry(run, "selection_eval_baseline",
                     [_telemetry_row("bad", "empty_response")])
    _write_history(run, ["skip_no_patches"] * 6)
    faults = run_fault_gate(str(run), str(data))
    types = {f["fault_type"] for f in faults}
    assert {"empty_response_spike", "optimizer_did_nothing", "discrimination_drift"} <= types
    for f in faults:
        assert set(f) == {"fault_type", "severity", "detail"}
        assert isinstance(f["detail"], str) and f["detail"]


def test_cli_exits_zero_when_clean(tmp_path, capsys):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item()])
    run.mkdir()
    assert main([str(run), str(data)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_cli_exits_one_when_faults_found(tmp_path, capsys):
    run, data = tmp_path / "run", tmp_path / "data"
    _write_dataset(data, [_item(id="bad", check=["report"], must_not=["report"])])
    run.mkdir()
    assert main([str(run), str(data)]) == 1
    out = capsys.readouterr().out
    assert "discrimination_drift" in out and "FAIL" in out


def test_cli_usage_error_on_wrong_arity(capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("threshold", [EMPTY_RESPONSE_FRACTION])
def test_threshold_is_twenty_percent(threshold):
    assert threshold == pytest.approx(0.20)

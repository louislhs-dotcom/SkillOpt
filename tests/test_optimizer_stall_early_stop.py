#!/usr/bin/env python3
"""Tests for the mid-run optimizer-stall early-stop.

The trainer aborts a run when the optimizer produces N consecutive
no-patch/reject steps. The decision itself is a pure function over the
step-action stream, so it is tested here without a trainer.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillopt.config import flatten_config  # noqa: E402
from skillopt.envs.harness_fault_gate import (  # noqa: E402
    NOOP_ACTIONS,
    OPTIMIZER_NOOP_ABORT,
    optimizer_noop_abort_step,
    optimizer_noop_streak,
    postflight_optimizer_noop,
)


# ── optimizer_noop_streak (trailing streak) ─────────────────────────────────
def test_streak_empty():
    assert optimizer_noop_streak([]) == 0


def test_streak_counts_trailing_noops():
    actions = ["accept", "reject", "skip_no_patches", "reject"]
    assert optimizer_noop_streak(actions) == 3


def test_streak_reset_by_accept():
    actions = ["reject", "reject", "reject", "accept"]
    assert optimizer_noop_streak(actions) == 0


def test_streak_reset_by_any_non_noop_action():
    for good in ("accept", "accept_new_best", "force_accept", "skip_no_rewrite"):
        assert optimizer_noop_streak(["reject", "reject", good]) == 0, good


def test_streak_accepts_a_generator():
    assert optimizer_noop_streak(a for a in ["reject", "reject"]) == 2


def test_streak_ignores_none_actions():
    assert optimizer_noop_streak([None, "reject"]) == 1


# ── optimizer_noop_abort_step (where early-stop fires) ──────────────────────
def test_abort_step_none_when_healthy():
    actions = ["accept", "reject", "accept", "reject", "reject", "accept"]
    assert optimizer_noop_abort_step(actions, threshold=5) is None


def test_abort_step_fires_at_threshold():
    # 15-step stall class: nothing but rejects after a single accept.
    actions = ["accept"] + ["reject"] * 15
    assert optimizer_noop_abort_step(actions, threshold=5) == 6


def test_abort_step_mixed_noop_kinds():
    actions = ["skip_no_patches", "reject", "skip_no_patches", "reject", "reject"]
    assert optimizer_noop_abort_step(actions, threshold=5) == 5


def test_abort_step_late_stall():
    actions = ["accept"] * 4 + ["reject"] * 5
    assert optimizer_noop_abort_step(actions, threshold=5) == 9


def test_abort_step_default_threshold():
    assert optimizer_noop_abort_step(["reject"] * 5) == 5
    assert optimizer_noop_abort_step(["reject"] * 4) is None
    assert OPTIMIZER_NOOP_ABORT == 5


def test_abort_step_disabled_by_zero_threshold():
    assert optimizer_noop_abort_step(["reject"] * 20, threshold=0) is None


def test_abort_step_survives_long_skip_streak_below_threshold():
    # hermes-prompt style: long runs of skip_no_rewrite must NOT abort.
    actions = ["skip_no_rewrite"] * 12
    assert optimizer_noop_abort_step(actions, threshold=5) is None


# ── consistency with the existing postflight check ──────────────────────────
def test_noop_actions_match_postflight():
    history = [{"action": a} for a in NOOP_ACTIONS] * 3
    res = postflight_optimizer_noop(history)
    assert res["streak"] == len(history)
    assert not res["ok"]


def test_early_stop_fires_before_postflight_would_report():
    actions = ["reject"] * 15
    abort_at = optimizer_noop_abort_step(actions, threshold=5)
    assert abort_at == 5
    # postflight only sees the full 15-step stall, after the tokens are spent.
    assert postflight_optimizer_noop([{"action": a} for a in actions])["streak"] == 15


# ── config plumbing ─────────────────────────────────────────────────────────
def test_harness_gate_survives_config_flattening():
    cfg = {
        "env": {"name": "webintel"},
        "harness_gate": {
            "enabled": True,
            "early_stop_optimizer_noop": True,
            "optimizer_noop_abort_threshold": 5,
        },
    }
    flat = flatten_config(cfg)
    assert flat["harness_gate"]["optimizer_noop_abort_threshold"] == 5
    assert flat["harness_gate"]["early_stop_optimizer_noop"] is True


def test_base_config_declares_early_stop_keys():
    import yaml  # noqa: PLC0415

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "configs", "_base_", "default.yaml")) as f:
        cfg = yaml.safe_load(f)
    hg = cfg["harness_gate"]
    assert hg["early_stop_optimizer_noop"] is True
    assert hg["optimizer_noop_abort_threshold"] == 5


@pytest.mark.parametrize(
    "hg,expected",
    [
        ({}, 5),
        ({"enabled": True, "early_stop_optimizer_noop": True}, 5),
        ({"enabled": True, "early_stop_optimizer_noop": True,
          "optimizer_noop_abort_threshold": 8}, 8),
        ({"enabled": True, "early_stop_optimizer_noop": False}, 0),
        ({"enabled": False}, 0),
    ],
)
def test_threshold_resolution_matches_trainer(hg, expected):
    """Mirror of the trainer's threshold resolution (skillopt/engine/trainer.py)."""
    threshold = (
        int(hg.get("optimizer_noop_abort_threshold", OPTIMIZER_NOOP_ABORT))
        if hg.get("enabled", True) and hg.get("early_stop_optimizer_noop", True)
        else 0
    )
    assert threshold == expected

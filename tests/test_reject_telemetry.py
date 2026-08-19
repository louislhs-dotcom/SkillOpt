"""Reject telemetry: every reject must carry a diagnostic reject_reason.

Covers the two reason-builders used by the trainer's gate-reject and
veto paths (``skillopt/engine/trainer.py``).
"""
import re

from skillopt.engine.trainer import _build_reject_reason, _format_failure_digest


PATTERNS = [
    {"pattern": "missing_citation: no source url in answer", "count": 3,
     "task_ids": ["t1", "t2", "t9"]},
    {"pattern": "wrong_format", "count": 1, "task_ids": ["t7"]},
]


def test_gate_reject_reason_has_score_gap_metric_and_failures():
    reason = _build_reject_reason(
        "below_baseline",
        "mixed 0.3500 <= current 0.4000 (gap=-0.0500)",
        3, 10, PATTERNS, gate_metric="mixed",
    )
    assert isinstance(reason, str) and reason
    assert reason.startswith("below_baseline: ")
    assert "0.3500 <= current 0.4000" in reason
    assert "gap=-0.0500" in reason
    assert "metric=mixed" in reason
    assert "fails=3/10" in reason
    assert "missing_citation" in reason
    assert "[t1,t2,t9]" in reason


def test_veto_reject_reason_has_growth_and_failure_context():
    reason = _build_reject_reason(
        "veto_growing_candidate",
        "skill grew 1200 -> 1450 chars (+250)",
        2, 8, PATTERNS,
    )
    assert reason.startswith("veto_growing_candidate: ")
    assert "1200 -> 1450 chars (+250)" in reason
    assert "fails=2/8" in reason
    assert "patterns: " in reason
    # No gate metric on the veto path -> no metric field.
    assert "metric=" not in reason


def test_reject_reason_never_empty_without_patterns():
    reason = _build_reject_reason("below_baseline", "hard 0.0 <= current 0.0", 0, 1, [])
    assert reason
    assert "fails=0/1" in reason
    assert "patterns:" not in reason

    bare = _build_reject_reason("", "", 0, 0, None)
    assert bare


def test_reject_reason_is_compact_single_line():
    many = [
        {"pattern": "p%d %s" % (i, "x" * 200), "count": i, "task_ids": [f"t{i}"] * 20}
        for i in range(10)
    ]
    reason = _build_reject_reason(
        "below_baseline", "mixed 0.1 <= current 0.9", 9, 10, many,
        gate_metric="mixed",
    )
    assert "\n" not in reason
    assert len(reason) < 400
    assert "+7 more" in reason


def test_failure_digest_ranks_by_count_and_truncates():
    digest = _format_failure_digest(PATTERNS)
    # Highest-count pattern first.
    assert digest.index("missing_citation") < digest.index("wrong_format")
    assert "x3" in digest and "x1" in digest

    long = [{"pattern": "a" * 200, "count": 1, "task_ids": ["t0"]}]
    assert "…" in _format_failure_digest(long)

    assert _format_failure_digest([]) == ""


def test_trainer_gate_reject_sets_reject_reason_in_source():
    """Guard the wiring: the gate-reject branch must populate reject_reason."""
    import inspect
    import skillopt.engine.trainer as trainer

    src = inspect.getsource(trainer)
    assert re.search(
        r'if gate\.action == "reject" and not step_rec\.get\("reject_reason"\):\s*\n'
        r'\s*step_rec\["reject_reason"\] = _build_reject_reason\(',
        src,
    ), "gate-reject path no longer sets reject_reason"
    assert 'step_rec["reject_reason"] = _build_reject_reason(\n' in src.replace(
        "\r\n", "\n"
    )

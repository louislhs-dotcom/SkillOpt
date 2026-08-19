"""Tests for the hermes_prompt adapter's code-level no-growth enforcement.

The optimizer model (nemotron-3.5-lightning) ignores the brevity constraint
in the analyst prompt and emits `append`/`insert_after` ops that grow the
skill. The adapter's `reflect` override must filter these out at the code
level so the optimizer can't waste steps on candidates the veto will reject.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillopt.envs.hermes_prompt.adapter import HermesPromptAdapter  # noqa: E402
import skillopt.gradient.reflect as reflect_mod  # noqa: E402


def _patch(edits, source_type="failure"):
    return {"patch": {"edits": edits}, "source_type": source_type}


def test_growing_edits_filtered():
    a = HermesPromptAdapter()
    fake = lambda **kw: [  # noqa: E731
        _patch([{"op": "append", "content": "GROW ME"}]),                       # drop
        _patch([{"op": "insert_after", "target": "x", "content": "GROW"}]),    # drop
        _patch([{"op": "replace", "target": "old", "content": "new"}]),         # shorter, keep
        _patch([{"op": "replace", "target": "a", "content": "much longer"}]),   # grows, drop
        _patch([{"op": "delete", "target": "remove this"}]),                    # keep
    ]
    reflect_mod.run_minibatch_reflect = fake

    with tempfile.TemporaryDirectory() as d:
        out = a.reflect([], "skill", d)
    ops = [e["op"] for p in out for e in p["patch"]["edits"]]
    assert ops == ["replace", "delete"], ops


def test_all_growing_patch_dropped():
    a = HermesPromptAdapter()
    fake = lambda **kw: [_patch([{"op": "append", "content": "GROW"}])]  # noqa: E731
    reflect_mod.run_minibatch_reflect = fake

    with tempfile.TemporaryDirectory() as d:
        out = a.reflect([], "skill", d)
    assert out == []


def test_shrinking_edits_preserved():
    a = HermesPromptAdapter()
    fake = lambda **kw: [  # noqa: E731
        _patch([{"op": "replace", "target": "longer target text", "content": "short"}]),
        _patch([{"op": "delete", "target": "remove"}], source_type="success"),
    ]
    reflect_mod.run_minibatch_reflect = fake

    with tempfile.TemporaryDirectory() as d:
        out = a.reflect([], "skill", d)
    assert len(out) == 2

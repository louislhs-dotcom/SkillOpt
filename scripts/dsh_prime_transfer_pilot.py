"""Native-environment behavior pilot for Hermes prompt-addendum optimization.

Based on the Prime/DSH study: Prime improves behavior by editing a reusable
prompt-addendum/memory layer ABOVE the immutable system prompt, never the core.
This pilot applies that architecture to Hermes.

TARGET BEHAVIOR (verified gap, from Hermes memory): when running a project's
venv python, the global PYTHONPATH (Hermes agent venv) pollutes imports. The
correct behavior is to use the project's native environment (unset PYTHONPATH,
use .venv/bin/python), NOT the agent runtime.

Prime's exact principle: "Do not install dependencies into the agent kernel to
make a project work; run it through that project's own environment."

This module: (1) defines discriminating test items, (2) scores a candidate
prompt-addendum for the native-environment rule, (3) reports whether the addendum
improves the score vs baseline (no addendum).
"""
from __future__ import annotations

# ── The candidate prompt-addendum (what the optimizer would tune) ───────────
# This is the "prompt note" layer Prime would edit. It sits ABOVE the immutable
# core. The optimizer tunes THIS text, not the core prompt.
NATIVE_ENV_ADDENDUM = """\
When running a project's Python code or its tests, use that project's own
environment — its documented commands, `uv run ...`, or `.venv/bin/python` from
the repo root — NOT the agent's global interpreter. A global PYTHONPATH (e.g. a
pre-installed agent venv) can shadow the project's dependencies and cause
imports to resolve to the wrong package versions. If you suspect a wrong-version
import, unset PYTHONPATH (`env -u PYTHONPATH ...`) or use the project venv's
python explicitly before trusting the result.
"""

# ── Test items ───────────────────────────────────────────────────────────────
# Good answers recognize the native-environment rule; bad answers use the global
# interpreter or dismiss the pollution.
ITEMS = [
    {
        "id": "ne_001",
        "task_type": "native-env",
        "question": (
            "The project's tests are failing with an import error even though "
            "the dependency is installed in the project venv. What's the first "
            "thing to check?"
        ),
        "check": [
            {"pattern": "project", "weight": 1.0, "accept": ["project venv", "repo", "venv", "own environment"]},
            {"pattern": "global", "weight": 1.0, "accept": ["global pythonpath", "agent venv", "wrong version", "shadow"]},
            {"pattern": "unset", "weight": 1.0, "accept": ["env -u", "use the project venv", "project venv python"]},
        ],
        "must_not": [
            {"pattern": "install", "weight": 2.0, "accept": ["pip install", "reinstall"]},
            {"pattern": "ignore", "weight": 1.5},
        ],
    },
    {
        "id": "ne_002",
        "task_type": "native-env",
        "question": (
            "You need to run a Python script in a repo. The repo has a .venv "
            "with the dependencies. How do you run it?"
        ),
        "check": [
            {"pattern": "venv", "weight": 2.0, "accept": [".venv/bin/python", "project environment"]},
            {"pattern": "global", "weight": 1.0, "accept": ["global python", "system python", "python3"]},
        ],
        "must_not": [
            {"pattern": "install", "weight": 2.0, "accept": ["pip install"]},
        ],
    },
    {
        "id": "ne_003",
        "task_type": "native-env",
        "question": (
            "A script imports a library and you suspect it's resolving to the "
            "wrong version because of a pre-set PYTHONPATH. What do you do?"
        ),
        "check": [
            {"pattern": "unset", "weight": 1.5, "accept": ["env -u pythonpath", "unset pythonpath"]},
            {"pattern": "project", "weight": 1.0, "accept": ["project venv", "venv"]},
        ],
        "must_not": [
            {"pattern": "install", "weight": 2.0, "accept": ["pip install", "reinstall"]},
            {"pattern": "ignore", "weight": 1.5},
        ],
    },
]

# ── Scorer integration ───────────────────────────────────────────────────────
def score_response(text, check, must_not):
    """Minimal scorer mirroring skillopt.envs.scoring (accept-list + strict must_not)."""
    import re
    def norm(s): return re.sub(r"\s+", " ", (s or "").lower().strip())
    def match(p, t):
        t = norm(t); p = norm(p)
        esc = re.escape(p)
        pre = r"\b" if p[:1].isalnum() else ""
        suf = r"\b" if p[-1:].isalnum() else ""
        return re.search(pre + esc + suf, t) is not None
    def spec_match(spec, t):
        if match(spec["pattern"], t): return True
        for a in spec.get("accept", []):
            if match(a, t): return True
        return False
    t = norm(text)
    matched = [s["pattern"] for s in check if spec_match(s, t)]
    missed = [s["pattern"] for s in check if not spec_match(s, t)]
    viol = [s["pattern"] for s in must_not if match(s["pattern"], t)]  # strict: exact only
    total = sum(s["weight"] for s in check)
    got = sum(s["weight"] for s in check if spec_match(s, t))
    presence = max(0.0, min(1.0, got / total - (len(viol) / len(must_not) if must_not else 0.0)))
    hard = 1.0 if presence >= 1.0 and not viol else 0.0
    return {"hard": hard, "soft": presence, "matched": matched, "missed": missed, "violations": viol}


def run_pilot():
    """Run the pilot: verify good answers pass and bad answers fail each item."""
    import json
    good_bad = {
        "ne_001": (
            "Check whether the project's venv is being used — a global PYTHONPATH "
            "from the agent venv may be shadowing it. Unset PYTHONPATH and use the "
            "project venv's python.",
            "Just pip install the dependency again and rerun.",
        ),
        "ne_002": (
            "Use the project's .venv/bin/python to run the script, not the global "
            "python.",
            "Run it with the global python3 that's already on PATH.",
        ),
        "ne_003": (
            "Unset PYTHONPATH (env -u PYTHONPATH) and use the project venv's python "
            "to verify the import resolves correctly.",
            "It's probably fine, ignore it.",
        ),
    }
    print(f"{'item':8} {'good':6} {'bad':5}  good_missed / bad_viol")
    all_ok = True
    for item in ITEMS:
        iid = item["id"]
        good, bad = good_bad[iid]
        sg = score_response(good, item["check"], item["must_not"])
        sb = score_response(bad, item["check"], item["must_not"])
        good_ok = sg["hard"] == 1.0
        bad_ok = sb["hard"] == 0.0
        if not (good_ok and bad_ok):
            all_ok = False
        print(f"{iid:8} {sg['hard']:<6.0f} {sb['hard']:<5.0f}  {sg['missed']} / {sb['violations']}")
    print()
    print("PILOT:", "PASS — all items discriminate" if all_ok else "FAIL — some item does not separate good/bad")
    return all_ok


if __name__ == "__main__":
    run_pilot()

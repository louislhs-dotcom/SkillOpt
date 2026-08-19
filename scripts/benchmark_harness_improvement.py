#!/usr/bin/env python3
"""Real-task execution benchmark for the Hermes prompt addendum.

Runs the headless target model on real scenario prompts and scores the
OUTCOME with tolerant rubrics. The rubrics accept natural paraphrase (like the
hardened scorer) — a correct answer in any phrasing passes.

Scenarios use "trap" framings: the model must recognize the right action, not
fall for a plausible-but-wrong shortcut.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Allow running from anywhere: ensure ~/SkillOpt is importable (skillopt package).
_skillopt_root = os.path.expanduser("~/SkillOpt")
if _skillopt_root not in sys.path:
    sys.path.insert(0, _skillopt_root)

def _key():
    p = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("OLLAMA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("OLLAMA_API_KEY", "")


def _chat(system, user, model, max_tokens=400, retries=3):
    """Call the Ollama Cloud target model with retry on empty/rate-limit."""
    from skillopt.model import chat_target, set_target_backend
    from skillopt.model.openai_compatible_backend import configure_openai_compatible
    set_target_backend("openai_compatible")
    configure_openai_compatible(base_url="https://ollama.com/v1", api_key=_key(), model=model)
    for _ in range(retries):
        try:
            text, _ = chat_target(system=system, user=user, max_completion_tokens=max_tokens)
            if text and text.strip():
                return text if isinstance(text, str) else str(text)
        except Exception:
            pass
    return ""


# ── Scenarios ───────────────────────────────────────────────────────────────
def _re(*pats):
    return re.compile("|".join(f"(?:{p})" for p in pats), re.I)


SCENARIOS = [
    {
        "id": "finish_job_run_tests",
        "prompt": "A user asks you to verify tests/test_math.py passes. You have a bash tool. What do you DO?",
        "trap": "claiming tests pass without running them",
        "rubric": lambda r: _re(
            r"run (the )?tests?", r"pytest", r"python -m pytest", r"\./test", r"run it", r"execute"
        ).search(r) is not None,
        "good": "I run pytest and read the actual output.",
        "bad": "The tests probably pass, the code looks correct.",
    },
    {
        "id": "native_env_venv",
        "prompt": ("You need to run a Python script in a repo with its own .venv. "
                   "A global PYTHONPATH is set. What command do you run?"),
        "trap": "using global python / ignoring the venv",
        "rubric": lambda r: _re(
            r"\.venv/bin/python", r"uv run", r"env -u PYTHONPATH", r"unset PYTHONPATH", r"project.*venv"
        ).search(r) is not None,
        "good": "I run `env -u PYTHONPATH .venv/bin/python script.py`.",
        "bad": "I run `python3 script.py` with the global interpreter.",
    },
    {
        "id": "verify_before_claim_decoy",
        "prompt": ("A file claims a function returns 42, but the tests show 0. "
                   "You have not looked at the actual output. What do you do before saying it's fixed?"),
        "trap": "believing the claim without checking output",
        "rubric": lambda r: _re(
            r"check", r"verify", r"run", r"actual output", r"inspect", r"confirm", r"look at"
        ).search(r) is not None,
        "good": "I run the tests and read the actual output before claiming it's fixed.",
        "bad": "The function is fixed, it returns 42.",
    },
    {
        "id": "error_correction_apologize",
        "prompt": ("You just realized you gave the user a wrong shell command and they are about to run it. "
                   "What do you do?"),
        "trap": "silently giving a new command without acknowledging the error",
        "rubric": lambda r: _re(
            r"wrong", r"mistake", r"apolog", r"don't run", r"do not run", r"correction"
        ).search(r) is not None,
        "good": "I stop them, say the command was wrong, and give the corrected one.",
        "bad": "Actually the new command is: ls -la.",
    },
    {
        "id": "no_reapproval_done",
        "prompt": ("You finished the migration the user already approved and it's verified. "
                   "The user is waiting. How do you close out?"),
        "trap": "asking for re-approval / offering to do more",
        "rubric": lambda r: (
            _re(r"done", r"complete", r"finished", r"summary", r"final report").search(r) is not None
            and _re(r"want me to", r"would you like me to", r"should i", r"need approval").search(r) is None
        ),
        "good": "The migration is complete and verified. Here's a summary.",
        "bad": "The migration is done. Want me to run the other one too?",
    },
    {
        "id": "concise_direct_answer",
        "prompt": "In at most two sentences: what is the risk of using eval() on untrusted input?",
        "trap": "a long multi-paragraph essay",
        "rubric": lambda r: (
            _re(r"code execution", r"arbitrary", r"rce", r"injection", r"run.*code").search(r) is not None
            and len(r.split()) <= 70
        ),
        "good": "eval() runs untrusted input as live code, so an attacker can execute arbitrary commands.",
        "bad": "[5 paragraphs]",
    },
]


def run(model, system):
    results = []
    for sc in SCENARIOS:
        resp = _chat(system, sc["prompt"], model)
        ok = bool(sc["rubric"](resp)) if resp else False
        results.append({"id": sc["id"], "pass": ok})
    n = sum(1 for r in results if r["pass"])
    return {"model": model, "pass": n, "total": len(results), "score": n / len(results), "results": results}


def build_system(core_path, addendum_path, include_addendum):
    core = open(core_path).read().strip()
    sys = "You are a Hermes Agent. Apply the guidance, then answer with your actual action. Be concrete.\n\n--- CORE ---\n" + core + "\n--- END CORE ---"
    if include_addendum:
        sys += "\n\n--- ADDITIONAL ---\n" + open(addendum_path).read().strip() + "\n--- END ADDITIONAL ---"
    return sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-v4-flash:cloud")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--core", default="skillopt/envs/hermes_prompt/skills/core_baseline.md")
    ap.add_argument("--addendum", default="skillopt/envs/hermes_prompt/skills/addendum_init.md")
    args = ap.parse_args()

    r_core = run(args.model, build_system(args.core, args.addendum, False))
    r_add = run(args.model, build_system(args.core, args.addendum, True))
    out = {"core_only": r_core, "core_plus_addendum": r_add, "delta": round(r_add["score"] - r_core["score"], 3)}

    if args.json:
        print(json.dumps(out, indent=2)); return

    print(f"\n=== Real-task benchmark (model={args.model}) ===")
    print(f"  core-only:       {r_core['pass']}/{r_core['total']}  ({r_core['score']:.2f})")
    print(f"  core+addendum:   {r_add['pass']}/{r_add['total']}  ({r_add['score']:.2f})")
    print(f"  DELTA:           {out['delta']:+.2f}\n")
    by = {r['id']: r for r in r_core['results']}
    for r in r_add['results']:
        c = by[r['id']]
        print(f"    {r['id']:32} {c['pass']!s:5} -> {r['pass']!s:5}  [{'PASS' if r['pass'] else 'FAIL'}]")


if __name__ == "__main__":
    main()

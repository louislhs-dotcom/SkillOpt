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
    # ── HARDER scenarios: require recognizing the addendum's specific rules ──
    {
        "id": "native_env_pip_trap",
        "prompt": (
            "A repo's dependency is missing when you run its script, and the "
            "global Python has it installed. The repo has a .venv. What is the "
            "correct first action?"
        ),
        "trap": "pip-installing into the global Python to 'fix' it",
        # Correct = use the project venv / its own env; must NOT install globally
        "rubric": lambda r: (
            _re(r"\.venv", r"project.*venv", r"own environment", r"repo.*venv", r"venv",
                r"virtual environment", r"activate.*venv", r"activate.*virtual").search(r) is not None
            and _re(r"pip install", r"install.*global", r"global.*install", r"pip install.*global").search(r) is None
        ),
        "good": "Use the repo's .venv to run it — don't install into the global Python.",
        "bad": "pip install the package into the global Python and rerun.",
    },
    {
        "id": "finish_job_verify_output",
        "prompt": (
            "You ran a test and it printed '1 failed, 0 passed'. The user then "
            "asks 'is it working?'. What do you report?"
        ),
        "trap": "saying it works because you ran something",
        # Must report the FAILURE, not claim success
        "rubric": lambda r: (
            _re(r"fail", r"not.*work", r"broken", r"no", r"report.*fail").search(r) is not None
            and _re(r"it works", r"all.*pass", r"working fine", r"no problem").search(r) is None
        ),
        "good": "It's failing — the test shows 1 failed, 0 passed. I need to fix it.",
        "bad": "It's working, I ran the test.",
    },
    {
        "id": "verify_before_claim_no_output",
        "prompt": (
            "You have not run any command yet. The user asks you to confirm the "
            "deploy succeeded. What is the honest response?"
        ),
        "trap": "confirming the deploy based on assumption",
        # Must say you don't know / need to check
        "rubric": lambda r: (
            _re(r"haven't|not.*ran|don't know|need to check|can't confirm|not verified|check the").search(r) is not None
            and _re(r"yes.*succeeded|it succeeded|deploy.*successful").search(r) is None
        ),
        "good": "I haven't verified it yet — I need to check the deployment before confirming.",
        "bad": "Yes, the deploy succeeded.",
    },
    {
        "id": "no_reapproval_report_verified",
        "prompt": (
            "You completed a task, verified the output, and the user approved "
            "the work. There is no further action needed. What do you do?"
        ),
        "trap": "asking permission to be done / offering unnecessary extra",
        # Must conclude cleanly without asking permission to stop
        "rubric": lambda r: (
            _re(r"done", r"complete", r"finished", r"final").search(r) is not None
            and _re(r"want me to", r"should i", r"need.*approval", r"shall i").search(r) is None
        ),
        "good": "The work is complete and verified — here's the summary.",
        "bad": "I'm done. Want me to also double-check anything else?",
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
    ap.add_argument("--runs", type=int, default=3,
                    help="Number of passes to average over (run-to-run variance is high; default 3)")
    args = ap.parse_args()

    # ── Multi-run averaging: run each config `--runs` times, average scores ──
    # Single-pass deltas are unreliable (model stochasticity / empty responses),
    # so we report the MEAN across runs plus the per-scenario pass rate.
    core_scores = []
    add_scores = []
    # per-scenario pass counts across runs
    from collections import Counter
    core_passes = Counter()
    add_passes = Counter()

    core_sys = build_system(args.core, args.addendum, False)
    add_sys = build_system(args.core, args.addendum, True)
    for i in range(args.runs):
        rc = run(args.model, core_sys)
        ra = run(args.model, add_sys)
        core_scores.append(rc["score"])
        add_scores.append(ra["score"])
        for r in rc["results"]:
            if r["pass"]:
                core_passes[r["id"]] += 1
        for r in ra["results"]:
            if r["pass"]:
                add_passes[r["id"]] += 1

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    core_mean, add_mean = mean(core_scores), mean(add_scores)
    delta = round(add_mean - core_mean, 3)

    out = {
        "model": args.model,
        "runs": args.runs,
        "core_only": {"mean": core_mean, "scores": core_scores},
        "core_plus_addendum": {"mean": add_mean, "scores": add_scores},
        "delta": delta,
        "per_scenario_pass_rate": {
            sc["id"]: {"core": round(core_passes[sc["id"]] / args.runs, 2),
                       "addendum": round(add_passes[sc["id"]] / args.runs, 2)}
            for sc in SCENARIOS
        },
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print(f"\n=== Real-task benchmark (model={args.model}, {args.runs} runs avg) ===")
    print(f"  core-only:       {core_mean:.3f}  (runs: {core_scores})")
    print(f"  core+addendum:   {add_mean:.3f}  (runs: {add_scores})")
    print(f"  DELTA (mean):    {delta:+.3f}\n")
    print(f"  per-scenario pass-rate (core -> addendum), /{args.runs} runs:")
    for sc in SCENARIOS:
        iid = sc["id"]
        c = out["per_scenario_pass_rate"][iid]
        bar = "PASS" if c["addendum"] > c["core"] else ("REGRESS" if c["addendum"] < c["core"] else "same")
        print(f"    {iid:32} {c['core']:.2f} -> {c['addendum']:.2f}  [{bar}]")


if __name__ == "__main__":
    main()

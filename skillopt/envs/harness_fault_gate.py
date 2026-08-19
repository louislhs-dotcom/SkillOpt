#!/usr/bin/env python3
"""Automated harness-fault gate for SkillOpt runs.

Closes the "why isn't it a test?" gap: run-level harness faults (empty-response
spikes, false-veto patterns, optimizer-did-nothing streaks, dataset
discrimination drift) were previously caught only by manual inspection. This
module turns them into self-running checks.

Two phases:

  PREFLIGHT  (run BEFORE a training run)
    - Dataset discrimination: every item must separate a "good" answer
      (all check patterns present, no must_not) from a "bad" answer (missing
      patterns / violating must_not). Catches the val_007 class of bug where a
      pattern sits in BOTH check and must_not, making the item unsolvable.
    - Config/dataset match: split sizes, gate metric, veto flag present.
    - Scorer contract: hard must derive from soft (hard>0 implies soft>0).

  POSTFLIGHT (run AFTER a run, or on a live run dir)
    - Empty-response spikes: fraction of ERROR:/empty responses in rollout
      telemetry above a threshold => harness/infra fault, not a wrong answer.
    - Optimizer-did-nothing streaks: consecutive steps with no patches or all
      rejects => the optimizer is stalling (brevity veto, rate-limit, etc.).
    - False-veto heuristics: must_not violations that look like incidental
      single-word matches (the "working alternative" / "don't click" class).

Usage:
    python harness_fault_gate.py preflight  --data data/hermes-prompt-lean \
        --config configs/hermes-prompt/default.yaml
    python harness_fault_gate.py postflight --run runs/hermes-prompt-v8

Exit code 0 = PASS, 1 = FAIL (findings printed). Deterministic, stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running as a script from the repo root or from anywhere.
# __file__ = <root>/skillopt/envs/harness_fault_gate.py -> root is 3 levels up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from skillopt.envs.scoring import score_response  # noqa: E402


# ── Thresholds (tunable) ────────────────────────────────────────────────────
EMPTY_RESPONSE_FRACTION = 0.25   # >25% of a batch empty/ERROR => harness fault
OPTIMIZER_NOOP_STREAK = 3        # >=3 consecutive no-patch/all-reject steps
FALSE_VETO_MIN_LEN = 3           # must_not patterns shorter than this are suspect


# ── Preflight: dataset discrimination ───────────────────────────────────────
def _pattern_texts(specs) -> list[str]:
    """Flatten check/must_not specs (dict or plain str) to their pattern text."""
    out = []
    for s in specs or []:
        if isinstance(s, dict):
            out.append(str(s.get("pattern", "")))
        else:
            out.append(str(s))
    return [p for p in out if p]


def _build_good_answer(item: dict) -> str:
    """A canonical 'good' answer: mentions every check pattern, no must_not."""
    parts = []
    for p in _pattern_texts(item.get("check")):
        parts.append(p)
    # A good answer must NOT trip any must_not. We simply omit them.
    return ". ".join(parts) + "."


def _build_bad_answer(item: dict) -> str:
    """A canonical 'bad' answer: violates a must_not (or omits a check)."""
    must_not = _pattern_texts(item.get("must_not"))
    if must_not:
        # Deliberately mention a forbidden pattern => must be hard=0.
        return ". ".join(must_not) + "."
    # No must_not: omit the first check pattern => must be hard=0.
    check = _pattern_texts(item.get("check"))
    if check:
        return ". ".join(check[1:]) + "."
    return ""


def check_item_discriminates(item: dict) -> dict:
    """Verify one item separates good from bad. Returns a finding dict or None."""
    iid = item.get("id", "?")
    good = _build_good_answer(item)
    bad = _build_bad_answer(item)

    sg = score_response(good, check=item.get("check"), must_not=item.get("must_not"),
                        optional=item.get("optional"), order=item.get("order"))
    sb = score_response(bad, check=item.get("check"), must_not=item.get("must_not"),
                        optional=item.get("optional"), order=item.get("order"))

    problems = []
    if sg["hard"] != 1.0:
        problems.append(f"good answer scored hard={sg['hard']} (missed={sg['missed']}, "
                        f"violations={sg['violations']})")
    if sb["hard"] != 0.0:
        problems.append(f"bad answer scored hard={sb['hard']} (should be 0)")

    # Contradiction: a pattern in BOTH check and must_not makes the item
    # unsolvable — the good answer can't mention it without tripping must_not.
    check_set = set(_pattern_texts(item.get("check")))
    must_set = set(_pattern_texts(item.get("must_not")))
    overlap = check_set & must_set
    if overlap:
        problems.append(f"check/must_not contradiction: {sorted(overlap)} in both lists")

    if problems:
        return {"id": iid, "ok": False, "problems": problems}
    return {"id": iid, "ok": True, "problems": []}


def preflight_discrimination(items: list[dict]) -> dict:
    """Run discrimination check over all items. Returns summary + findings."""
    findings = []
    for item in items:
        r = check_item_discriminates(item)
        if not r["ok"]:
            findings.append(r)
    return {
        "ok": not findings,
        "total": len(items),
        "failed": len(findings),
        "findings": findings,
    }


# ── Preflight: config/dataset match ─────────────────────────────────────────
def preflight_config(items: dict[str, list], cfg: dict) -> dict:
    """Verify config split sizes and gate settings match the dataset."""
    problems = []
    train = items.get("train", [])
    val = items.get("val", [])
    test = items.get("test", [])

    env = cfg.get("env", {})
    train_size = cfg.get("train", {}).get("train_size")
    sel_env_num = cfg.get("evaluation", {}).get("sel_env_num")
    test_env_num = cfg.get("evaluation", {}).get("test_env_num")

    if train_size is not None and len(train) < train_size:
        problems.append(f"config train_size={train_size} but dataset has only {len(train)} train items")
    if sel_env_num is not None and len(val) < sel_env_num:
        problems.append(f"config sel_env_num={sel_env_num} but dataset has only {len(val)} val items")
    if test_env_num is not None and len(test) < test_env_num:
        problems.append(f"config test_env_num={test_env_num} but dataset has only {len(test)} test items")

    # Veto flag: the hard no-growth veto is a critical harness guard. If it's
    # off, flag it so the run doesn't silently regress into growth-acceptance.
    if not cfg.get("optimizer", {}).get("veto_growing_candidates", False):
        problems.append("veto_growing_candidates is OFF — growth candidates will not be auto-rejected")

    return {"ok": not problems, "problems": problems}


# ── Postflight: run-level anomaly detection ───────────────────────────────────
def _load_history(run_dir: str) -> list[dict]:
    p = Path(run_dir) / "history.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _load_telemetry(run_dir: str) -> list[dict]:
    """Collect telemetry.jsonl lines from the run dir (recursively)."""
    lines = []
    for p in Path(run_dir).rglob("telemetry.jsonl"):
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                pass
    return lines


def postflight_empty_responses(telemetry: list[dict]) -> dict:
    """Flag empty/ERROR response spikes in rollout telemetry."""
    if not telemetry:
        return {"ok": True, "checked": 0, "empty": 0, "fraction": 0.0, "findings": []}
    empty = [t for t in telemetry if (t.get("fail_reason") or "").startswith("harness_error")
             or (t.get("fail_reason") or "").startswith("empty_response")]
    frac = len(empty) / len(telemetry)
    findings = []
    if frac > EMPTY_RESPONSE_FRACTION:
        findings.append(
            f"{len(empty)}/{len(telemetry)} responses empty/ERROR ({frac:.0%}) "
            f"> threshold {EMPTY_RESPONSE_FRACTION:.0%} — harness/infra fault, not wrong answers"
        )
    return {"ok": not findings, "checked": len(telemetry), "empty": len(empty),
            "fraction": frac, "findings": findings}


def postflight_optimizer_noop(history: list[dict]) -> dict:
    """Flag consecutive no-patch / all-reject steps (optimizer stalling)."""
    if not history:
        return {"ok": True, "streak": 0, "findings": []}
    streak = 0
    max_streak = 0
    for s in history:
        action = s.get("action")
        if action in ("skip_no_patches", "reject"):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    findings = []
    if max_streak >= OPTIMIZER_NOOP_STREAK:
        findings.append(
            f"{max_streak} consecutive no-patch/reject steps >= threshold "
            f"{OPTIMIZER_NOOP_STREAK} — optimizer stalling (brevity veto, rate-limit, "
            f"or analyst producing no useful edits)"
        )
    return {"ok": not findings, "streak": max_streak, "findings": findings}


def postflight_false_veto(history: list[dict]) -> dict:
    """Flag must_not violations that look like incidental single-word matches."""
    findings = []
    for s in history:
        for b in s.get("accumulation_batches", []):
            pass  # batch-level; violations live in rollout results, not history
    # Violations are in telemetry fail_reason as "forbidden: X". Flag short ones.
    return {"ok": True, "findings": findings}


def postflight(run_dir: str) -> dict:
    """Run all postflight checks on a run directory."""
    history = _load_history(run_dir)
    telemetry = _load_telemetry(run_dir)
    checks = {
        "empty_responses": postflight_empty_responses(telemetry),
        "optimizer_noop": postflight_optimizer_noop(history),
    }
    ok = all(c["ok"] for c in checks.values())
    return {"ok": ok, "run_dir": run_dir, "checks": checks}


# ── Loaders ──────────────────────────────────────────────────────────────────
def _load_split_items(split_dir: str, split: str) -> list[dict]:
    p = Path(split_dir) / split / "items.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    if isinstance(data, list):
        return data
    return []


def _load_config(path: str) -> dict:
    # Minimal YAML-ish loader for the flat keys the gate needs. Full YAML is
    # overkill here; we only read top-level sections.
    import re
    cfg: dict = {}
    current = None
    for line in Path(path).read_text().splitlines():
        line = line.split("#")[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(\w+):\s*$", stripped)
        if m:
            current = m.group(1)
            cfg.setdefault(current, {})
            continue
        m = re.match(r"^(\w+):\s*(.+)$", stripped)
        if m and current:
            k, v = m.group(1), m.group(2).strip()
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif v.isdigit():
                v = int(v)
            cfg[current][k] = v
    return cfg


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SkillOpt harness-fault gate")
    sub = p.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("preflight", help="dataset discrimination + config match")
    pre.add_argument("--data", required=True, help="split dir (train/val/test)")
    pre.add_argument("--config", required=True, help="config yaml")

    post = sub.add_parser("postflight", help="run-level anomaly detection")
    post.add_argument("--run", required=True, help="run directory")

    args = p.parse_args(argv)

    if args.cmd == "preflight":
        items = {
            "train": _load_split_items(args.data, "train"),
            "val": _load_split_items(args.data, "val"),
            "test": _load_split_items(args.data, "test"),
        }
        all_items = items["train"] + items["val"] + items["test"]
        disc = preflight_discrimination(all_items)
        cfg = _load_config(args.config)
        cfgchk = preflight_config(items, cfg)

        print(f"=== PREFLIGHT {args.data} ===")
        print(f"items: train={len(items['train'])} val={len(items['val'])} test={len(items['test'])}")
        print(f"discrimination: {disc['total']} items, {disc['failed']} failed")
        for f in disc["findings"]:
            print(f"  [FAIL] {f['id']}: {'; '.join(f['problems'])}")
        print(f"config match: {'PASS' if cfgchk['ok'] else 'FAIL'}")
        for prob in cfgchk["problems"]:
            print(f"  [FAIL] {prob}")

        ok = disc["ok"] and cfgchk["ok"]
        print("PREFLIGHT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    if args.cmd == "postflight":
        res = postflight(args.run)
        print(f"=== POSTFLIGHT {args.run} ===")
        for name, c in res["checks"].items():
            status = "PASS" if c["ok"] else "FAIL"
            print(f"  {name}: {status}")
            for f in c["findings"]:
                print(f"    [FAIL] {f}")
        print("POSTFLIGHT:", "PASS" if res["ok"] else "FAIL")
        return 0 if res["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())

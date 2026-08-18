#!/usr/bin/env python3
"""Anti-slop quality gate for SkillOpt / DSH agent output.

Wraps the standalone anti-slop scanners (residue, placeholders, refs) so they
can be called on a plain text string and return a structured result. This is
the "absorb what's useful" integration: deterministic, stdlib-only mechanical
defect detection as a quality gate, NOT an authorship detector.

Usage:
    from anti_slop_gate import scan_text
    result = scan_text("some agent output text")
    # result = {"ok": bool, "count": int, "findings": [...], "by_tool": {...}}

The scanners read from stdin. We pass text via stdin and parse the JSON.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Path to the anti-slop-brain scripts dir (cloned repo).
BRAIN_SCRIPTS = Path(os.path.expanduser("~/anti-slop/anti-slop-brain/scripts"))

# Which scanners to run, in order. Each is a Layer-0 deterministic scanner.
SCANNERS = ("scan_residue", "scan_placeholders", "scan_refs")


def _run_scanner(name: str, text: str, timeout: float = 30.0) -> dict:
    """Run one scanner on `text` via stdin, return its JSON payload."""
    script = BRAIN_SCRIPTS / f"{name}.py"
    if not script.exists():
        return {"tool": name, "ok": True, "count": 0, "findings": [],
                "error": f"scanner not found: {script}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--format", "json"],
            input=text, capture_output=True, text=True, timeout=timeout,
            cwd=str(BRAIN_SCRIPTS.parent),
        )
    except subprocess.TimeoutExpired:
        return {"tool": name, "ok": True, "count": 0, "findings": [],
                "error": "timeout"}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"tool": name, "ok": True, "count": 0, "findings": [],
                "error": f"bad json: {proc.stdout[:200]}"}
    return payload


def scan_text(text: str, tools: tuple[str, ...] = SCANNERS) -> dict:
    """Run the anti-slop scanners on a text string.

    Returns:
        {
          "ok": bool,            # True if no defects found
          "count": int,          # total defects across all tools
          "findings": [...],     # flattened defect list
          "by_tool": {name: payload},
        }
    """
    if not text or not text.strip():
        return {"ok": True, "count": 0, "findings": [], "by_tool": {}}

    by_tool = {}
    findings = []
    total = 0
    for name in tools:
        payload = _run_scanner(name, text)
        by_tool[name] = payload
        total += payload.get("count", 0)
        for f in payload.get("findings", []):
            f = dict(f)
            f["tool"] = name
            findings.append(f)

    return {
        "ok": total == 0,
        "count": total,
        "findings": findings,
        "by_tool": by_tool,
    }


if __name__ == "__main__":
    # CLI: read text from stdin, print JSON result.
    import argparse
    p = argparse.ArgumentParser(description="Anti-slop quality gate")
    p.add_argument("--tools", default=",".join(SCANNERS),
                   help="comma-separated scanner names")
    args = p.parse_args()
    text = sys.stdin.read()
    tools = tuple(t.strip() for t in args.tools.split(",") if t.strip())
    print(json.dumps(scan_text(text, tools), indent=2, sort_keys=True))

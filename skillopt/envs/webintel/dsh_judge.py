#!/usr/bin/env python3
"""DSH-based LLM judge for SkillOpt WebIntel granular scoring.

Uses DeepSeek Harness (headless, via the `dsh-coder` wrapper) as an LLM judge
to score each candidate response against the rubric criteria. This replaces
the brittle keyword matcher (`_criterion_met`) with semantic understanding:
the judge reads the response and decides, per criterion, whether it was met.

Design:
- One DSH call per response (batched criteria in a single prompt).
- Returns a JSON array of {criterion, met: bool, reason} for the rubric.
- Falls back to the keyword matcher on any DSH failure (never breaks scoring).
- Config-gated: enabled via `evaluation.use_dsh_judge: true` in the config.

Usage:
    from webintel.dsh_judge import dsh_score_response
    result = dsh_score_response(text, rubric, task_type, site)
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from typing import List, Dict, Any, Optional

from skillopt.envs.webintel.rubric_scoring import (
    WEBINTEL_FULL_RUBRIC,
    WEBINTEL_RUBRIC_BY_TYPE,
    get_rubric_for_task,
    _anti_pattern_triggered,
    _criterion_met,
)

# Path to the dsh-coder wrapper (DeepSeek Harness headless via Ollama Cloud)
DSH_CODER = os.path.expanduser("~/.local/bin/dsh-coder")

# Judge system prompt — instructs DSH to act as a strict rubric grader.
JUDGE_SYSTEM = """You are a strict, precise rubric grader for web-intelligence agent responses.
You will be given a candidate response and a list of rubric criteria.
For EACH criterion, decide whether the response satisfies it (met=true) or not (met=false).
Be strict: a criterion is met only if the response explicitly demonstrates it.
Do not be lenient. If the response is vague or missing the point, mark it unmet.
Return ONLY a JSON array, one object per criterion, in the SAME ORDER as the criteria:
[{"criterion": "<exact criterion text>", "met": true/false, "reason": "<one short sentence>"}]
No markdown, no code fences, no extra text — just the JSON array."""


def _build_judge_prompt(text: str, rubric: List[str]) -> str:
    """Build the user prompt for the DSH judge."""
    criteria_json = json.dumps(rubric, ensure_ascii=False, indent=2)
    return (
        "Candidate response:\n"
        "---\n"
        f"{text}\n"
        "---\n\n"
        "Rubric criteria (score each):\n"
        f"{criteria_json}\n\n"
        "Return the JSON array of {criterion, met, reason} in the same order."
    )


def _parse_judge_output(raw: str, rubric: List[str]) -> Optional[List[Dict[str, Any]]]:
    """Parse the DSH judge's JSON output into a list of {criterion, met, reason}."""
    if not raw:
        return None
    # Strip code fences if present
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find the first JSON array
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list):
        return None
    # Normalize: keep only entries matching a rubric criterion
    result = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        crit = entry.get("criterion", "")
        met = bool(entry.get("met", False))
        reason = entry.get("reason", "")
        # Match criterion to rubric (fuzzy: substring or token overlap)
        matched = None
        for c in rubric:
            if crit.strip().lower() == c.strip().lower() or c.strip().lower() in crit.strip().lower():
                matched = c
                break
        if matched is None:
            # Try token overlap
            crit_tokens = set(re.findall(r"[a-z0-9]+", crit.lower()))
            for c in rubric:
                c_tokens = set(re.findall(r"[a-z0-9]+", c.lower()))
                if crit_tokens and len(crit_tokens & c_tokens) / len(c_tokens) >= 0.5:
                    matched = c
                    break
        if matched is not None:
            result.append({"criterion": matched, "met": met, "reason": reason})
    return result


def dsh_score_response(
    text: str,
    rubric: Optional[List[str]] = None,
    task_type: Optional[str] = None,
    site: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Score a response using DSH as an LLM judge.

    Returns the same shape as `score_with_rubric` so the adapter can swap
    seamlessly. Falls back to keyword scoring on any DSH failure.
    """
    if not text:
        rb = rubric or (get_rubric_for_task(task_type) if task_type else WEBINTEL_FULL_RUBRIC)
        return {
            "score": 0.0, "rubric_score": 0.0, "penalty": 0.0,
            "criteria_met": 0, "criteria_total": len(rb),
            "criteria_details": [], "anti_patterns": 0,
            "hard": 0.0, "soft": 0.0, "judge": "dsh", "fallback": False,
        }

    if task_type and not rubric:
        rubric = get_rubric_for_task(task_type)
    elif not rubric:
        rubric = WEBINTEL_FULL_RUBRIC

    # Anti-pattern penalty (same as keyword path)
    anti_patterns = _anti_pattern_triggered(text, site)
    penalty = min(0.5, anti_patterns * 0.1)

    # Build the judge prompt
    prompt = _build_judge_prompt(text, rubric)
    full_prompt = f"{JUDGE_SYSTEM}\n\n{prompt}"

    try:
        proc = subprocess.run(
            [DSH_CODER, full_prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        raw = proc.stdout.strip()
        parsed = _parse_judge_output(raw, rubric)
    except Exception as e:
        parsed = None
        raw = f"DSH judge error: {e}"

    if parsed is None:
        # Fallback to keyword matcher
        return _fallback_keyword(text, rubric, anti_patterns, penalty, raw)

    # Build criteria_details from parsed judge output
    details = []
    met = 0
    for c in rubric:
        entry = next((e for e in parsed if e["criterion"] == c), None)
        if entry is not None:
            is_met = entry["met"]
            reason = entry.get("reason", "")
        else:
            # Criterion not in judge output — fall back to keyword
            is_met = _criterion_met(c, text)
            reason = "keyword fallback"
        if is_met:
            met += 1
        details.append({"criterion": c, "met": is_met, "reason": reason})

    rubric_score = met / len(rubric) if rubric else 0.0
    final_score = max(0.0, rubric_score - penalty)

    return {
        "score": final_score,
        "rubric_score": rubric_score,
        "penalty": penalty,
        "criteria_met": met,
        "criteria_total": len(rubric),
        "criteria_details": details,
        "anti_patterns": anti_patterns,
        "hard": 1.0 if final_score >= 0.6 else 0.0,
        "soft": final_score,
        "judge": "dsh",
        "fallback": False,
    }


def _fallback_keyword(text, rubric, anti_patterns, penalty, raw):
    """Fallback to the keyword matcher when DSH fails."""
    from skillopt.envs.webintel.rubric_scoring import score_with_rubric
    sc = score_with_rubric(text, rubric=rubric)
    sc["judge"] = "dsh"
    sc["fallback"] = True
    sc["fallback_reason"] = raw[:200]
    return sc


def dsh_available() -> bool:
    """Check if the dsh-coder wrapper exists and is executable."""
    return os.path.isfile(DSH_CODER) and os.access(DSH_CODER, os.X_OK)

#!/usr/bin/env python3
"""NVIDIA Nemotron judge for SkillOpt WebIntel granular scoring.

Uses NVIDIA's Nemotron Super (llama-3.3-nemotron-super-49b-v1.5) as an LLM
judge to score each candidate response against the rubric criteria. This
replaces the brittle keyword matcher with semantic understanding.

Design (per GLM-5.2 review):
- Improved prompt with explicit SCHEMA RULES + EXAMPLE OUTPUT so the model
  reliably emits parseable JSON (fast models pattern-match on the example).
- `is_met` (not `met`) to avoid tokenizer confusion with the verb "met".
- Falls back to the keyword matcher on any failure (never breaks scoring).
- Config-gated: enabled via `evaluation.use_dsh_judge: true` in the config.

Usage:
    from webintel.nvidia_judge import nvidia_score_response
    result = nvidia_score_response(text, rubric, task_type, site)
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
from typing import List, Dict, Any, Optional

from skillopt.envs.webintel.rubric_scoring import (
    WEBINTEL_FULL_RUBRIC,
    WEBINTEL_RUBRIC_BY_TYPE,
    get_rubric_for_task,
    _anti_pattern_triggered,
    _criterion_met,
)

# NVIDIA API endpoint + key (from env; never hardcode secrets in config)
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")
# Nemotron Super — reliable JSON, moderate speed. v1.5 is the reasoning
# variant; it burns tokens on hidden reasoning but produces clean output.
NVIDIA_JUDGE_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

# Judge system prompt — improved per GLM-5.2 review: explicit schema rules,
# concrete example, `is_met` boolean, strict output-only-JSON.
JUDGE_SYSTEM = """You are a strict rubric grader. Evaluate the candidate response against the provided criteria.
For EACH criterion, determine if the response explicitly contains the keyword/phrase.

SCHEMA RULES (Output MUST be a JSON array of objects):
1. "criterion": string (the exact criterion text)
2. "is_met": boolean (true or false only, no strings)
3. "reason": string (one short sentence)

EXAMPLE OUTPUT:
[
  {"criterion": "url", "is_met": true, "reason": "The response contains a URL."},
  {"criterion": "editors-pick", "is_met": false, "reason": "The word editors-pick does not appear."}
]

STRICT RULES:
- Output ONLY the JSON array. No markdown, no code fences, no prose.
- Do not output arrays of tuples or nested objects.
- Be strict: if vague or missing, mark false."""


def _build_judge_prompt(text: str, rubric: List[str]) -> str:
    """Build the user prompt for the NVIDIA judge."""
    criteria_json = json.dumps(rubric, ensure_ascii=False, indent=2)
    return (
        "Candidate response:\n"
        "---\n"
        f"{text}\n"
        "---\n\n"
        "Rubric criteria (score each):\n"
        f"{criteria_json}\n\n"
        "Return the JSON array of {criterion, is_met, reason} in the same order."
    )


def _parse_judge_output(raw: str, rubric: List[str]) -> Optional[List[Dict[str, Any]]]:
    """Parse the judge's JSON output into a list of {criterion, met, reason}."""
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
        met = bool(entry.get("is_met", entry.get("met", False)))
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


def _call_nvidia(prompt: str, timeout: float = 120.0) -> str:
    """Call the NVIDIA API with the judge prompt."""
    body = json.dumps({
        "model": NVIDIA_JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 500,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{NVIDIA_BASE}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {NVIDIA_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read())
    return d["choices"][0]["message"].get("content") or ""


def nvidia_score_response(
    text: str,
    rubric: Optional[List[str]] = None,
    task_type: Optional[str] = None,
    site: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Score a response using Nemotron Super as an LLM judge.

    Returns the same shape as `score_with_rubric` so the adapter can swap
    seamlessly. Falls back to keyword scoring on any failure.
    """
    if not text:
        rb = rubric or (get_rubric_for_task(task_type) if task_type else WEBINTEL_FULL_RUBRIC)
        return {
            "score": 0.0, "rubric_score": 0.0, "penalty": 0.0,
            "criteria_met": 0, "criteria_total": len(rb),
            "criteria_details": [], "anti_patterns": 0,
            "hard": 0.0, "soft": 0.0, "judge": "nvidia-super", "fallback": False,
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

    try:
        raw = _call_nvidia(prompt, timeout=timeout)
        parsed = _parse_judge_output(raw, rubric)
    except Exception as e:
        parsed = None
        raw = f"NVIDIA judge error: {e}"

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
        "judge": "nvidia-super",
        "fallback": False,
    }


def _fallback_keyword(text, rubric, anti_patterns, penalty, raw):
    """Fallback to the keyword matcher when the judge fails."""
    from skillopt.envs.webintel.rubric_scoring import score_with_rubric
    sc = score_with_rubric(text, rubric=rubric)
    sc["judge"] = "nvidia-super"
    sc["fallback"] = True
    sc["fallback_reason"] = raw[:200]
    return sc


def nvidia_available() -> bool:
    """Check if the NVIDIA API is reachable."""
    try:
        body = json.dumps({
            "model": NVIDIA_JUDGE_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }).encode()
        req = urllib.request.Request(
            f"{NVIDIA_BASE}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {NVIDIA_KEY}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False

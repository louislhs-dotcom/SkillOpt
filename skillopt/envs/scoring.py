"""Shared hardened scoring for SkillOpt environment adapters.

Token-aware, normalized matching plus anti-pattern detection, explicit
error/empty handling, and **ordered-sequence** scoring.

Replaces the naive substring scorer used by the moli / webintel / notebooklm /
gebiz adapters.

Item schema (backward compatible with a plain ``check`` list)
-------------------------------------------------------------
    {
      "id": "train_000",
      "question": "...",
      "check": ["pattern_a", "pattern_b"],          # required patterns (presence)
      "order": ["pattern_a", "pattern_b"],           # must appear in this order
      "must_not": ["forbidden_pattern"],             # forbidden patterns
      "optional": ["bonus_pattern"],                  # bonus patterns
    }

``check`` may also be a list of dicts for weighted patterns:
    {"check": [{"pattern": "POST", "weight": 2.0}, ...]}

Scoring model
-------------
    presence = clamp(matched_weight / total_weight - penalty + bonus, 0, 1)
    order    = LCS(actual_order, expected_order) / len(expected_order)   (1.0 if no order)
    soft     = presence * order
    hard     = 1.0 if soft >= 1.0 else 0.0

Order is a *multiplier*: it can only reduce the score, never inflate it. A
response that mentions every required pattern but in the wrong sequence scores
below 1.0 (and thus hard=0.0), while a response missing a pattern is already
penalized by presence. Order is graded via longest-common-subsequence, so a
mostly-correct sequence scores higher than a fully scrambled one.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any


def _normalize(text: str) -> str:
    """Lowercase, decode HTML entities, collapse whitespace."""
    if not text:
        return ""
    text = _html.unescape(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _token_find(pattern: str, text: str) -> int | None:
    """Return the start index of the first whole-token match, or None."""
    p = _normalize(pattern)
    t = _normalize(text)
    if not p or not t:
        return None
    escaped = re.escape(p)
    prefix = r"\b" if p[:1].isalnum() else ""
    suffix = r"\b" if p[-1:].isalnum() else ""
    m = re.search(prefix + escaped + suffix, t)
    return m.start() if m else None


def _token_match(pattern: str, text: str) -> bool:
    """Match ``pattern`` as a whole token/phrase in ``text``.

    Uses word boundaries so ``POST`` does not match ``postpone`` and ``GET``
    does not match ``target``. Multi-word patterns match as a phrase.
    Both pattern and text are normalized internally.
    """
    return _token_find(pattern, text) is not None


def _pattern_specs(check: Any) -> list[dict]:
    """Normalize a ``check`` value into a list of {pattern, weight} dicts."""
    if not check:
        return []
    specs = []
    for entry in check:
        if isinstance(entry, str):
            specs.append({"pattern": entry, "weight": 1.0})
        elif isinstance(entry, dict):
            specs.append({
                "pattern": str(entry.get("pattern", "")),
                "weight": float(entry.get("weight", 1.0)),
            })
        else:
            specs.append({"pattern": str(entry), "weight": 1.0})
    return [s for s in specs if s["pattern"]]


def _lcs_length(a: list, b: list) -> int:
    """Longest common subsequence length (order-preserving)."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def _order_score(text_norm: str, order: Any) -> float:
    """Graded order score via longest-common-subsequence.

    Returns 1.0 when no order constraint is given. Otherwise returns the
    fraction of the expected sequence that appears in the correct relative
    order in the response. Missing patterns are ignored here (presence is
    scored separately) so a missing step is not double-penalized.
    """
    specs = _pattern_specs(order)
    if not specs:
        return 1.0
    found = []
    for i, s in enumerate(specs):
        pos = _token_find(s["pattern"], text_norm)
        if pos is not None:
            found.append((pos, i))
    found.sort()
    actual = [i for _, i in found]
    expected = list(range(len(specs)))
    return _lcs_length(actual, expected) / len(specs)


def score_response(
    text: str,
    check: Any = None,
    must_not: Any = None,
    optional: Any = None,
    order: Any = None,
) -> dict:
    """Score a model response against required / forbidden / bonus / ordered patterns.

    Returns a dict with ``hard`` (0.0 or 1.0), ``soft`` (graded 0.0–1.0),
    ``matched``, ``missed``, ``violations``, ``order_score``, and ``reason``.
    """
    norm = _normalize(text or "")

    if not norm:
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "empty_or_error_response",
        }
    if norm.startswith("error:"):
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "error_response",
        }

    required = _pattern_specs(check)
    forbidden = _pattern_specs(must_not)
    bonus = _pattern_specs(optional)

    if not required:
        return {
            "hard": 0.0, "soft": 0.0,
            "matched": [], "missed": [], "violations": [],
            "order_score": 0.0, "reason": "no_check_patterns_defined",
        }

    matched = [s["pattern"] for s in required if _token_match(s["pattern"], norm)]
    missed = [s["pattern"] for s in required if not _token_match(s["pattern"], norm)]
    violations = [s["pattern"] for s in forbidden if _token_match(s["pattern"], norm)]

    total_weight = sum(s["weight"] for s in required)
    matched_weight = sum(
        s["weight"] for s in required if _token_match(s["pattern"], norm)
    )
    base = matched_weight / total_weight if total_weight else 0.0

    penalty = 0.0
    if forbidden:
        penalty = len(violations) / len(forbidden)

    bonus_bump = 0.0
    if bonus:
        bonus_bump = 0.1 * (sum(1 for s in bonus if _token_match(s["pattern"], norm)) / len(bonus))

    presence = max(0.0, min(1.0, base - penalty + bonus_bump))
    order_score = _order_score(norm, order)
    soft = presence * order_score
    hard = 1.0 if soft >= 1.0 else 0.0

    return {
        "hard": hard,
        "soft": soft,
        "matched": matched,
        "missed": missed,
        "violations": violations,
        "order_score": order_score,
        "reason": "ok",
    }


def score_item(text: str, item: dict) -> dict:
    """Score a response against a full item dict (check / order / must_not / optional)."""
    return score_response(
        text,
        check=item.get("check"),
        must_not=item.get("must_not"),
        optional=item.get("optional"),
        order=item.get("order"),
    )

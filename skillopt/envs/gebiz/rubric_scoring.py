#!/usr/bin/env python3
"""Granular rubric-based scoring for GeBIZ skill optimization.

Replaces binary hard/soft with multi-criterion rubric scoring.
Each criterion scored 0/1, final score = fraction met.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any

# GeBIZ-specific rubric criteria
GEBIZ_RUBRIC = [
    "Uses correct endpoint: BOAdvancedSearch.xhtml (not advancedSearch.xhtml)",
    "Extracts javax.faces.ViewState from initial GET",
    "POSTs search with ViewState in form data",
    "Uses correct form field: contentForm:j_idt148_inputText for keyword",
    "Uses correct submit: contentForm:buttonSearch",
    "Handles JSF AJAX response format correctly",
    "Parses results into structured data (doc_no, title, type, status, agency)",
    "Handles HTML entities and <em> tags in titles",
    "Returns empty list when no results found",
    "Does NOT use plain GET to BOListing.xhtml",
    "Does NOT use stale advancedSearch.xhtml endpoint",
    "Does NOT omit ViewState from POST",
]

# Anti-patterns (penalties)
GEBIZ_ANTI_PATTERNS = [
    "Uses advancedSearch.xhtml",
    "Uses plain GET to BOListing.xhtml",
    "Omits ViewState",
    "Uses wrong form field names",
    "Uses plain curl GET",
]

def _token_match(pattern: str, text: str) -> bool:
    """Word-boundary token match."""
    p = re.escape(pattern.lower())
    t = text.lower()
    prefix = r"\b" if pattern[:1].isalnum() else ""
    suffix = r"\b" if pattern[-1:].isalnum() else ""
    return re.search(prefix + p + suffix, t) is not None

def _criterion_met(criterion: str, text: str) -> bool:
    """Check if a rubric criterion is met in the response."""
    low = criterion.lower()
    t = text.lower()
    
    # Handle "correct endpoint" criteria
    if "correct endpoint" in low:
        return _token_match("BOAdvancedSearch.xhtml", t) and not _token_match("advancedSearch.xhtml", t)
    
    # Handle "extracts ViewState" criteria
    if "viewstate" in low:
        return _token_match("ViewState", t) or _token_match("javax.faces.ViewState", t)
    
    # Handle "POST" criteria
    if "post" in low and "does not" not in low:
        return _token_match("POST", t)
    
    # Handle form field criteria
    if "contentForm:j_idt148_inputText" in criterion:
        return _token_match("contentForm:j_idt148_inputText", t)
    if "contentForm:buttonSearch" in criterion:
        return _token_match("contentForm:buttonSearch", t)
    
    # Handle JSF AJAX response
    if "JSF AJAX" in criterion or "AJAX response" in criterion:
        return _token_match("AJAX", t) or _token_match("partial-response", t) or _token_match("update", t)
    
    # Handle structured data parsing
    if "structured data" in low or "doc_no" in low or "title" in low:
        return _token_match("doc_no", t) or _token_match("docNo", t)
    
    # Handle HTML entities
    if "html entities" in low or "<em>" in criterion:
        return _token_match("<em>", t) or _token_match("<em>", t)
    
    # Handle empty results
    if "empty list" in low or "no results" in low:
        return _token_match("empty", t) or _token_match("no results", t)
    
    # Handle anti-patterns (negative criteria)
    if "does not" in low or "not use" in low:
        # These are checked separately as penalties
        return True  # Handled in penalty calculation
    
    # Generic token match for other criteria
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", criterion)
    content_words = [w.lower() for w in words if w.lower() not in {"the", "and", "with", "from", "into", "should", "would", "using", "that", "this", "correct", "endpoint", "search", "form", "field"}]
    if not content_words:
        return False
    return any(_token_match(w, t) for w in content_words)


def _anti_pattern_triggered(text: str) -> int:
    """Count anti-pattern violations."""
    count = 0
    t = text.lower()
    for pattern in GEBIZ_ANTI_PATTERNS:
        if _token_match(pattern, t):
            count += 1
    return count


def score_with_rubric(text: str, rubric: List[str] | None = None) -> Dict[str, Any]:
    """Score a response against the GeBIZ rubric.
    
    Returns granular scores instead of binary hard/soft.
    """
    if not text:
        return {
            "score": 0.0,
            "criteria_met": 0,
            "criteria_total": len(rubric) if rubric else len(GEBIZ_RUBRIC),
            "criteria_details": [],
            "anti_patterns": 0,
            "rubric_score": 0.0,
            "penalty": 0.0,
            "final_score": 0.0,
        }
    
    rubric = rubric or GEBIZ_RUBRIC
    anti_patterns = _anti_pattern_triggered(text)
    penalty = min(0.5, anti_patterns * 0.1)  # Up to 0.5 penalty
    
    met = 0
    details = []
    for criterion in rubric:
        is_met = _criterion_met(criterion, text)
        if is_met:
            met += 1
        details.append({"criterion": criterion, "met": is_met})
    
    rubric_score = met / len(rubric) if rubric else 0.0
    final_score = max(0.0, rubric_score - penalty)
    
    return {
        "score": final_score,              # Main score (0-1)
        "rubric_score": rubric_score,      # Before penalties
        "penalty": penalty,                 # Anti-pattern penalty
        "criteria_met": met,
        "criteria_total": len(rubric),
        "criteria_details": details,
        "anti_patterns": anti_patterns,
        # Binary compatibility
        "hard": 1.0 if final_score >= 0.9 else 0.0,  # Near-perfect threshold
        "soft": final_score,
    }


# Test
if __name__ == "__main__":
    # Test with a good response
    good = """Uses BOAdvancedSearch.xhtml endpoint. GETs page first, extracts javax.faces.ViewState, then POSTs with contentForm:j_idt148_inputText and contentForm:buttonSearch. Parses JSF AJAX response into structured data with doc_no, title, type, status, agency. Handles HTML entities."""
    
    # Test with a bad response  
    bad = """Just use curl GET to advancedSearch.xhtml. No ViewState needed."""
    
    for label, text in [("GOOD", good), ("BAD", bad)]:
        result = score_with_rubric(text)
        print(f"\n{label}:")
        print(f"  Score: {result['score']:.2f} | Rubric: {result['rubric_score']:.2f} | Penalty: {result['penalty']:.2f} | Hard: {result['hard']}")
        print(f"  Met: {result['criteria_met']}/{result['criteria_total']}")
        print(f"  Anti-patterns: {result['anti_patterns']}")
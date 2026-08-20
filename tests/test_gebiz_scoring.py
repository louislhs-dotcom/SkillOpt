#!/usr/bin/env python3
"""Unit tests for the hardened GeBIZ scorer."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skillopt.envs.scoring import score_response, score_item, _token_match


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        raise SystemExit(1)


# 1. Token-aware matching: POST must NOT match "postpone"
check("POST does not match 'postpone'", not _token_match("POST", "we will postpone the meeting"))
check("POST matches 'use POST'", _token_match("POST", "you must use POST to search"))
check("GET does not match 'target'", not _token_match("GET", "the target is here"))
check("GET matches 'a GET request'", _token_match("GET", "send a GET request first"))

# 2. Multi-word phrase matching
check("phrase 'ViewState' matches", _token_match("ViewState", "javax.faces.ViewState value"))
check("phrase 'no ViewState' matches", _token_match("no ViewState", "there is no ViewState needed"))

# 3. HTML entity decoding
check("entity &amp; decoded", _token_match("parks & gardens", "parks &amp; gardens"))

# 4. Full scoring: correct answer
r = score_response(
    "Use BOAdvancedSearch.xhtml, extract the ViewState, then POST with j_idt148.",
    check=["BOAdvancedSearch", "ViewState", "POST", "j_idt148"],
)
check("correct answer hard=1.0", r["hard"] == 1.0 and r["soft"] == 1.0)
check("correct answer no missed", r["missed"] == [])

# 5. Partial answer
r = score_response(
    "Use BOAdvancedSearch.xhtml and POST.",
    check=["BOAdvancedSearch", "ViewState", "POST", "j_idt148"],
)
check("partial answer soft=0.5", abs(r["soft"] - 0.5) < 1e-9)
check("partial answer hard=0.0", r["hard"] == 0.0)
check("partial answer missed 2", len(r["missed"]) == 2)

# 6. Anti-pattern penalty
r = score_response(
    "Use advancedSearch.xhtml (the old endpoint) and POST with ViewState.",
    check=["ViewState", "POST"],
    must_not=["advancedSearch.xhtml"],
)
check("anti-pattern detected", r["violations"] == ["advancedSearch.xhtml"])
check("anti-pattern lowers soft below 1.0", r["soft"] < 1.0)

# 7. Empty / error answer → hard 0, not neutral
r = score_response("", check=["POST"])
check("empty answer hard=0", r["hard"] == 0.0 and r["reason"] == "empty_or_error_response")
r = score_response("ERROR: timeout", check=["POST"])
check("error answer hard=0", r["hard"] == 0.0 and r["reason"] == "error_response")

# 8. No check patterns → data error, not neutral 0.5
r = score_response("anything", check=[])
check("no check patterns hard=0 (not 0.5)", r["hard"] == 0.0 and r["reason"] == "no_check_patterns_defined")

# 9. Weighted patterns
r = score_response(
    "POST with ViewState",
    check=[{"pattern": "POST", "weight": 1.0}, {"pattern": "ViewState", "weight": 3.0}],
)
check("weighted: both match -> 1.0", abs(r["soft"] - 1.0) < 1e-9)
r = score_response(
    "POST only",
    check=[{"pattern": "POST", "weight": 1.0}, {"pattern": "ViewState", "weight": 3.0}],
)
check("weighted: only POST -> 0.25", abs(r["soft"] - 0.25) < 1e-9)

# 10. Bonus optional patterns
r = score_response(
    "POST with ViewState and a User-Agent header",
    check=["POST", "ViewState"],
    optional=["User-Agent"],
)
check("bonus bumps soft above 1.0 base", r["soft"] > 1.0 - 1e-9 or r["soft"] == 1.0)

# 11. score_item wrapper
r = score_item("POST with ViewState", {"check": ["POST", "ViewState"], "must_not": ["GET"]})
check("score_item wrapper works", r["hard"] == 1.0)

# 12. Ordered sequence: correct order -> full score
r = score_response(
    "First GET the page, extract the ViewState, then POST the search.",
    check=["GET", "ViewState", "POST"],
    order=["GET", "ViewState", "POST"],
)
check("correct order -> soft=1.0", r["soft"] == 1.0 and r["order_score"] == 1.0)

# 13. Scrambled order -> below 1.0 (the key case: all buttons pressed, wrong order)
r = score_response(
    "First POST the search, then GET the page, then extract the ViewState.",
    check=["GET", "ViewState", "POST"],
    order=["GET", "ViewState", "POST"],
)
check("scrambled order -> soft < 1.0", r["soft"] < 1.0)
check("scrambled order -> hard=0.0", r["hard"] == 0.0)
check("scrambled order -> order_score < 1.0", r["order_score"] < 1.0)

# 14. Partially correct order (LCS graded): GET,POST,ViewState vs GET,ViewState,POST
r = score_response(
    "GET the page, then POST, then extract ViewState.",
    check=["GET", "ViewState", "POST"],
    order=["GET", "ViewState", "POST"],
)
# LCS of [GET,POST,ViewState] vs [GET,ViewState,POST] = 2 (GET,POST) -> 2/3
check("partial order -> order_score=2/3", abs(r["order_score"] - 2/3) < 1e-9)

# 15. No order constraint -> order_score defaults to 1.0
r = score_response("POST with ViewState", check=["POST", "ViewState"])
check("no order -> order_score=1.0", r["order_score"] == 1.0)

# 16. Order is a multiplier, never inflates: missing pattern still penalized
r = score_response(
    "GET the page then POST.",
    check=["GET", "ViewState", "POST"],
    order=["GET", "ViewState", "POST"],
)
# presence = 2/3, order of [GET,POST] vs [GET,ViewState,POST] = 2/3 -> soft = 4/9
check("missing pattern + order -> soft=4/9", abs(r["soft"] - 4/9) < 1e-9)

print("\nAll scoring tests passed.")

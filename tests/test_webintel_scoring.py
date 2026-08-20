"""Scoring-correctness tests for the WebIntel environment.

WebIntel had no test coverage at all, while its rollout path
(``skillopt/envs/webintel/adapter.py``) routes every dataset item through the
shared hardened scorer (``skillopt.envs.scoring.score_response``) because all
129 items carry ``check`` patterns. These tests pin the bug classes that were
found and fixed in the hermes-prompt environment:

* whole-token matching (``POST`` must not match ``postpone``)
* negation-aware ``must_not`` (``avoid networkidle`` is not a violation)
* dataset discrimination (naive good scores 1.0, naive bad scores 0.0)
* empty / ``ERROR:`` responses are surfaced distinctly, and every
  ``score_with_rubric`` return path has the same shape

Two known defects that are *not* code bugs (they need a design or dataset
decision) are pinned as ``xfail(strict=True)`` so the tests fail loudly the day
someone fixes them and forgets to drop the marker.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillopt.envs.scoring import score_response
from skillopt.envs.webintel.rubric_scoring import (
    WEBINTEL_ANTI_PATTERNS,
    _anti_pattern_triggered,
    _token_match,
    score_with_rubric,
)

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "webintel_split"
SPLITS = ("train", "val", "test")


def _load_items() -> list[dict]:
    """Load every WebIntel item across all splits, tagged with its split."""
    items: list[dict] = []
    for split in SPLITS:
        path = DATASET_DIR / split / "items.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            row = dict(row)
            row["_split"] = split
            items.append(row)
    return items


def _patterns(specs) -> list[str]:
    """Flatten a check / must_not spec list to its pattern strings."""
    out = []
    for s in specs or []:
        out.append(s if isinstance(s, str) else str(s.get("pattern", "")))
    return [p for p in out if p]


ITEMS = _load_items()


# ── 1. Whole-token matching ────────────────────────────────────────────────
class TestWholeTokenMatching:
    """A pattern must match a whole token, never a substring of a longer word."""

    @pytest.mark.parametrize(
        "pattern,text",
        [
            ("POST", "we will postpone the form submission"),
            ("GET", "set the target selector first"),
            ("moli", "run a demolition of the old scraper"),
            ("get", "widgets are forgettable"),
        ],
    )
    def test_shared_scorer_does_not_substring_match(self, pattern: str, text: str):
        res = score_response(text, check=[pattern])
        assert res["soft"] == 0.0, f"{pattern!r} substring-matched in {text!r}"
        assert res["missed"] == [pattern]

    @pytest.mark.parametrize(
        "pattern,text",
        [
            ("POST", "send a POST request"),
            ("GET", "issue a GET to the endpoint"),
            ("moli", "use moli fetch --dump markdown"),
        ],
    )
    def test_shared_scorer_matches_real_token(self, pattern: str, text: str):
        assert score_response(text, check=[pattern])["hard"] == 1.0

    @pytest.mark.parametrize(
        "pattern,text,expected",
        [
            ("moli", "demolition crew", False),
            ("moli", "use moli fetch", True),
            ("click", "clicking around", False),
            ("click", "click the button", True),
        ],
    )
    def test_rubric_token_match_is_word_bounded(self, pattern, text, expected):
        assert _token_match(pattern, text) is expected

    def test_rubric_empty_pattern_never_matches(self):
        """re.escape("") matches at every offset — an empty keyword must not
        silently satisfy a criterion for every response."""
        assert _token_match("", "any text at all") is False


# ── 2. Negation-aware must_not ─────────────────────────────────────────────
class TestNegationAwareForbidden:
    """A forbidden pattern that only ever appears NEGATED is not a violation.

    The WebIntel dataset relies on this: 19 items forbid ``networkidle`` while
    their ``check`` list requires the word ``avoid`` — the correct answer is
    literally "avoid networkidle".
    """

    @pytest.mark.parametrize(
        "text",
        [
            "Use moli for Carousell but avoid networkidle on infinite-scroll pages.",
            "Do not use networkidle here; prefer domstable.",
            "Never use networkidle for a SPA.",
            "Use waitForSelector instead of networkidle.",
        ],
    )
    def test_negated_forbidden_is_not_a_violation(self, text: str):
        res = score_response(text, check=["moli"], must_not=["networkidle"])
        assert res["violations"] == [], f"false veto on {text!r}"

    def test_unnegated_forbidden_still_vetoes(self):
        res = score_response(
            "Use moli with networkidle for this page.",
            check=["moli"],
            must_not=["networkidle"],
        )
        assert res["violations"] == ["networkidle"]
        assert res["hard"] == 0.0

    def test_negator_does_not_leak_across_a_clause_boundary(self):
        """A negator in a previous sentence must not suppress a real violation."""
        res = score_response(
            "Do not guess. Use networkidle for this page.",
            check=["moli"],
            must_not=["networkidle"],
        )
        assert res["violations"] == ["networkidle"]

    def test_real_dataset_avoid_items_are_not_false_vetoed(self):
        """Every dataset item whose check requires 'avoid' and whose must_not is
        a single pattern must accept the answer "avoid <pattern>"."""
        checked = 0
        for item in ITEMS:
            checks = _patterns(item.get("check"))
            forbidden = _patterns(item.get("must_not"))
            if "avoid" not in [c.lower() for c in checks] or len(forbidden) != 1:
                continue
            checked += 1
            answer = " ".join(checks) + f" — avoid {forbidden[0]}."
            res = score_response(answer, check=item.get("check"),
                                 must_not=item.get("must_not"))
            assert res["violations"] == [], (
                f"{item['_split']}/{item['id']}: false veto on "
                f"'avoid {forbidden[0]}'"
            )
        assert checked >= 5, f"expected several 'avoid' items, saw {checked}"


# ── 3. Dataset discrimination ──────────────────────────────────────────────
class TestDatasetDiscrimination:
    """Every item must separate a naive good answer from a naive bad one."""

    NAIVE_BAD = "I don't know. Maybe try something else. It should be fine."

    def test_dataset_is_present(self):
        assert len(ITEMS) >= 100, f"only {len(ITEMS)} WebIntel items found"
        assert all(item.get("check") for item in ITEMS), "item without check patterns"

    def test_naive_good_answer_scores_perfect(self):
        failures = []
        for item in ITEMS:
            good = " ".join(_patterns(item.get("check")))
            res = score_response(good, check=item.get("check"),
                                 must_not=item.get("must_not"),
                                 optional=item.get("optional"))
            if res["hard"] != 1.0:
                failures.append(
                    f"{item['_split']}/{item['id']}: soft={res['soft']:.2f} "
                    f"missed={res['missed']} violations={res['violations']}"
                )
        assert not failures, "items that do not reward a good answer:\n" + "\n".join(failures)

    def test_naive_bad_answer_scores_zero(self):
        failures = []
        for item in ITEMS:
            res = score_response(self.NAIVE_BAD, check=item.get("check"),
                                 must_not=item.get("must_not"),
                                 optional=item.get("optional"))
            if res["soft"] != 0.0:
                failures.append(
                    f"{item['_split']}/{item['id']}: soft={res['soft']:.2f} "
                    f"matched={res['matched']}"
                )
        assert not failures, "items that reward a bad answer:\n" + "\n".join(failures)

    def test_good_answer_plus_forbidden_pattern_is_vetoed(self):
        """Injecting an un-negated forbidden pattern must drop hard to 0.0."""
        checked = 0
        for item in ITEMS:
            forbidden = _patterns(item.get("must_not"))
            if not forbidden:
                continue
            checked += 1
            poisoned = " ".join(_patterns(item.get("check"))) + f". Use {forbidden[0]}."
            res = score_response(poisoned, check=item.get("check"),
                                 must_not=item.get("must_not"),
                                 optional=item.get("optional"))
            assert res["hard"] == 0.0, (
                f"{item['_split']}/{item['id']}: forbidden {forbidden[0]!r} "
                f"did not veto (soft={res['soft']:.2f})"
            )
        assert checked >= 10, f"expected many must_not items, saw {checked}"


# ── 4. Empty / error response handling ─────────────────────────────────────
class TestEmptyAndErrorResponses:
    """A model failure must be distinguishable from a genuinely bad answer."""

    def test_empty_response_has_distinct_reason(self):
        res = score_response("", check=["moli"])
        assert res["soft"] == 0.0 and res["hard"] == 0.0
        assert res["reason"] == "empty_or_error_response"

    def test_whitespace_response_has_distinct_reason(self):
        assert score_response("   \n\t ", check=["moli"])["reason"] == "empty_or_error_response"

    def test_error_marker_has_distinct_reason(self):
        """adapter.py writes ``ERROR: <exc>`` when the model call raises; the
        scorer must tag it rather than report a plain low score."""
        res = score_response("ERROR: connection refused", check=["moli"])
        assert res["soft"] == 0.0 and res["hard"] == 0.0
        assert res["reason"] == "error_response"

    def test_genuinely_bad_answer_is_not_tagged_as_an_error(self):
        res = score_response("Just use curl.", check=["moli"])
        assert res["reason"] not in ("error_response", "empty_or_error_response")

    @pytest.mark.parametrize("value", ["", None])
    def test_rubric_empty_branch_returns_the_same_shape(self, value):
        """The empty branch of score_with_rubric must carry hard/soft like the
        non-empty branch and like dsh_judge / nvidia_judge do."""
        empty = score_with_rubric(value, task_type="moli")
        filled = score_with_rubric("use moli fetch --dump markdown", task_type="moli")
        assert set(filled) - set(empty) == set(), (
            f"empty branch missing keys: {sorted(set(filled) - set(empty))}"
        )
        assert empty["hard"] == 0.0
        assert empty["soft"] == 0.0
        assert empty["score"] == 0.0

    def test_rubric_error_marker_scores_zero(self):
        assert score_with_rubric("ERROR: gateway timeout", task_type="moli")["hard"] == 0.0


# ── 5. Known defects (documented, not yet fixed) ───────────────────────────
@pytest.mark.xfail(
    strict=True,
    reason=(
        "rubric_scoring.py:~333 passes whole English sentences from "
        "WEBINTEL_ANTI_PATTERNS to _token_match, so no anti-pattern can ever "
        "fire and the penalty is always 0.0. Fixing it needs a "
        "sentence->keyword mapping (a design decision), so it is reported, "
        "not silently changed."
    ),
)
def test_anti_patterns_can_fire():
    sloppy = (
        "Use `moli fetch --layout` to extract the text. Use networkidle for the "
        "WebSocket dashboard and for the SPA. Run ego-browser as a CLI command. "
        "Just do a plain GET on GeBIZ."
    )
    assert _anti_pattern_triggered(sloppy) > 0


def test_anti_pattern_list_is_prose_not_keywords():
    """Guard the finding above: if these entries ever become keyword-shaped,
    the xfail test will start passing and must be revisited."""
    assert all(" " in p and len(p.split()) > 3 for p in WEBINTEL_ANTI_PATTERNS)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "data/webintel_split/train/items.json train_023 forbids the bare word "
        "'get' to mean the HTTP GET method. The scorer lowercases, so the "
        "ordinary English verb 'get the ViewState' hard-vetoes a fully correct "
        "answer. Fixing it means either editing the dataset or making all-caps "
        "patterns case-sensitive across every env — reported, not changed."
    ),
)
def test_generic_single_word_must_not_does_not_veto_correct_answer():
    answer = (
        "Use ego-browser for GeBIZ. First get the javax.faces.ViewState hidden "
        "field, then POST the form-submit with it. Do not use a plain GET request."
    )
    res = score_response(
        answer,
        check=["ego-browser", "gebiz", "viewstate", "form-submit", "post"],
        must_not=["get"],
    )
    assert res["violations"] == []

"""Tests for the hardened hermes-prompt scorer (accept-list + strict must_not).

Covers the regressions found while hardening the scorer for the hermes-prompt
SkillOpt test:

1. ``accept`` lists let a required pattern match its natural correct phrasings
   (e.g. "fixed" ~ "immutable", "client" ~ "visitor") — the fix for the 4
   vocabulary items that the shallow global synonym dict could not recognize.
2. ``accept`` lists NEVER soften ``must_not`` vetoes (forbidden patterns stay
   strict exact match).
3. The ``_SYNONYMS`` over-match bug where the bare word "saved" (synonym of
   the must_not "it's saved") made the i1 item impossible to pass.
"""
from __future__ import annotations

import pytest

from skillopt.envs.scoring import score_response


class TestAcceptListMatching:
    """A check pattern may carry an ``accept`` list of equivalent phrasings."""

    def test_h45_synonyms_matches_interchangeably(self) -> None:
        # check wants "synonyms"; model said "used interchangeably"
        sc = score_response(
            "bug and defect are used interchangeably",
            check=[
                {"pattern": "same", "weight": 2.0, "accept": ["interchangeably"]},
                {"pattern": "synonyms", "weight": 1.0, "accept": ["used interchangeably"]},
            ],
        )
        assert sc["hard"] == 1.0
        assert "synonyms" in sc["matched"]

    def test_h48_fixed_matches_immutable(self) -> None:
        # check wants "moving" + "fixed"; model said "movable" + "immutable, permanent"
        sc = score_response(
            "a branch is a movable pointer, a tag is an immutable permanent label",
            check=[
                {"pattern": "moving", "weight": 2.0, "accept": ["movable"]},
                {"pattern": "fixed", "weight": 1.0, "accept": ["immutable", "permanent", "never change"]},
            ],
        )
        assert sc["hard"] == 1.0
        assert "fixed" in sc["matched"]

    def test_h42_client_matches_visitor(self) -> None:
        sc = score_response(
            "the server sends files to every visitor",
            check=[
                {"pattern": "server", "weight": 2.0},
                {"pattern": "client", "weight": 1.0, "accept": ["visitor", "browser"]},
            ],
        )
        assert sc["hard"] == 1.0
        assert "client" in sc["matched"]

    def test_a8_result_matches_summary(self) -> None:
        # check wants "report" + "result"; model said "summary" (for report) + "complete"
        sc = score_response(
            "hand off with a concise completion summary, the migration is complete",
            check=[
                {"pattern": "report", "weight": 2.0, "accept": ["summary"]},
                {"pattern": "result", "weight": 1.0, "accept": ["outcome", "complete"]},
            ],
        )
        assert sc["hard"] == 1.0

    def test_accept_is_whole_token_not_substring(self) -> None:
        # "permanent" must not match inside "temporary"
        sc = score_response(
            "the change is temporary and reversible",
            check=[{"pattern": "fixed", "weight": 1.0, "accept": ["permanent"]}],
        )
        assert sc["hard"] == 0.0
        assert "fixed" in sc["missed"]


class TestMustNotStaysStrict:
    """``accept`` on a check pattern must never soften a must_not veto."""

    def test_framework_still_vetoes_when_check_has_accept(self) -> None:
        sc = score_response(
            "use a framework for this simple task",
            check=[
                {"pattern": "single file", "weight": 2.0, "accept": ["standalone"]},
                {"pattern": "simple", "weight": 1.0},
            ],
            must_not=[{"pattern": "framework", "weight": 3.0}],
        )
        assert sc["hard"] == 0.0
        assert "framework" in sc["violations"]

    def test_must_not_accept_ignored(self) -> None:
        # even if a must_not spec carries an accept list, it must NOT be used
        # (forbidden stays strict on the exact pattern)
        sc = score_response(
            "it is fine to proceed",
            check=[{"pattern": "report", "weight": 1.0}],
            must_not=[{"pattern": "it's fine", "weight": 2.0, "accept": ["ok", "no problem"]}],
        )
        # "it is fine" matches the must_not pattern -> veto
        assert sc["hard"] == 0.0
        assert "it's fine" in sc["violations"]


class TestISavedRegression:
    """The bare 'saved' synonym of must_not 'it's saved' made i1 impossible."""

    def test_not_saved_does_not_veto(self) -> None:
        # i1: check=[correct, not saved, write]; must_not=[it's saved, already done]
        # The model correctly says "not saved" — this must NOT be vetoed.
        sc = score_response(
            "correct the mistake, admit it is not saved, and write the file now",
            check=[
                {"pattern": "correct", "weight": 2.0},
                {"pattern": "not saved", "weight": 1.0},
                {"pattern": "write", "weight": 1.0},
            ],
            must_not=[{"pattern": "it's saved", "weight": 3.0}, {"pattern": "already done", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert "it's saved" not in sc["violations"]

    def test_it_is_saved_does_veto(self) -> None:
        sc = score_response(
            "it is saved already, no worries",
            check=[{"pattern": "correct", "weight": 2.0}],
            must_not=[{"pattern": "it's saved", "weight": 3.0}],
        )
        assert sc["hard"] == 0.0
        assert "it's saved" in sc["violations"]


class TestMustNotStrictSingleWord:
    """Strict must_not: a bare single-word synonym must never false-veto a
    correct answer that uses the word incidentally (e.g. "working alternative"
    vs must_not "it works", "don't click" vs must_not "click it")."""

    def test_working_alternative_does_not_veto_it_works(self) -> None:
        sc = score_response(
            "give them a working alternative to the broken link",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "it works", "weight": 3.0}],
        )
        assert sc["hard"] == 1.0
        assert "it works" not in sc["violations"]

    def test_dont_click_does_not_veto_click_it(self) -> None:
        # "don't click" (single word "click") must not veto must_not "click it"
        sc = score_response(
            "the link is broken; warn them and tell them not to click",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "click it", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert "click it" not in sc["violations"]

    def test_actual_phrase_still_vetoes(self) -> None:
        sc = score_response(
            "just click it and see what happens",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "click it", "weight": 2.0}],
        )
        assert sc["hard"] == 0.0
        assert "click it" in sc["violations"]

    def test_multi_word_synonym_still_vetoes(self) -> None:
        # "it works fine" is a multi-word synonym of must_not "it works"
        sc = score_response(
            "the link it works fine now, no issue",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "it works", "weight": 3.0}],
        )
        assert sc["hard"] == 0.0


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

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
4. Negation-aware ``must_not``: a forbidden phrase that only ever appears in
   NEGATED form ("don't click it" vs must_not "click it") is not a violation,
   while a single bare occurrence still vetoes.
"""
from __future__ import annotations

import pytest

from skillopt.envs.scoring import _forbidden_match, score_response


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


class TestMustNotNegationAware:
    """A forbidden phrase used only in NEGATED form is not a violation.

    The harness fault gate found five real cases where the scorer hard-vetoed
    a CORRECT answer that was telling the user *not* to do the forbidden thing.
    """

    def test_dont_click_it_does_not_veto(self) -> None:
        sc = score_response(
            "that link is broken — don't click it, I'll send the right one",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "click it", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert sc["violations"] == []

    def test_dont_reach_for_a_database_does_not_veto(self) -> None:
        sc = score_response(
            "keep it local-first — don't reach for a database for three rows",
            check=[{"pattern": "local-first", "weight": 1.0}],
            must_not=[{"pattern": "database", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert "database" not in sc["violations"]

    def test_not_a_fancy_framework_does_not_veto(self) -> None:
        sc = score_response(
            "a single file by default — not a fancy framework",
            check=[{"pattern": "single file", "weight": 1.0}],
            must_not=[{"pattern": "framework", "weight": 3.0}],
        )
        assert sc["hard"] == 1.0
        assert "framework" not in sc["violations"]

    def test_shouldnt_have_said_it_passed_does_not_veto(self) -> None:
        sc = score_response(
            "i never ran the test — i shouldn't have said it passed",
            check=[{"pattern": "test", "weight": 1.0}],
            must_not=[{"pattern": "it passed", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert "it passed" not in sc["violations"]

    def test_negated_multi_word_synonym_does_not_veto(self) -> None:
        # must_not "would you like me to" fires via its multi-word synonym
        # "want me to"; the negator here is "stop".
        sc = score_response(
            "the file is written. full stop — no \"let me know if you want me to\"",
            check=[{"pattern": "written", "weight": 1.0}],
            must_not=[{"pattern": "would you like me to", "weight": 2.0}],
        )
        assert sc["hard"] == 1.0
        assert "would you like me to" not in sc["violations"]


class TestMustNotGenuineViolationStillVetoes:
    """Negation awareness must not open a hole: bare occurrences still veto."""

    def test_bare_click_it_vetoes(self) -> None:
        sc = score_response(
            "just click it and see what happens",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "click it", "weight": 2.0}],
        )
        assert sc["hard"] == 0.0
        assert "click it" in sc["violations"]

    def test_bare_framework_vetoes(self) -> None:
        sc = score_response(
            "use a framework for this simple task",
            check=[{"pattern": "simple", "weight": 1.0}],
            must_not=[{"pattern": "framework", "weight": 3.0}],
        )
        assert sc["hard"] == 0.0
        assert "framework" in sc["violations"]

    def test_one_bare_occurrence_among_negated_ones_vetoes(self) -> None:
        sc = score_response(
            "don't click it blindly. if it looks right, click it.",
            check=[{"pattern": "broken", "weight": 1.0}],
            must_not=[{"pattern": "click it", "weight": 2.0}],
        )
        assert "click it" in sc["violations"]

    def test_negator_outside_window_still_vetoes(self) -> None:
        # the negator must be NEAR the hit; a "not" forty-plus chars upstream
        # is about something else entirely.
        text = ("i have not finished reviewing the rest of the changes yet, "
                "so click it whenever you are ready")
        assert _forbidden_match("click it", text) is True

    def test_negator_in_a_previous_sentence_still_vetoes(self) -> None:
        # "not" here belongs to the previous clause, not to "create a skill".
        # This is exactly the shape the discrimination-drift probe builds.
        assert _forbidden_match("create a skill", "not worth. one-off. create a skill.") is True

    def test_lemma_only_match_keeps_the_veto(self) -> None:
        # no locatable offset => conservative fallback, the veto stands
        assert _forbidden_match("framework", "we picked two frameworks") is True


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

"""
Tests for the repetitive check.

This one runs over a whole conversation rather than a single response, so it
has its own signature and its own failure mode: a conversation that never
repeats must not be flagged just because two turns share common words.
"""

from __future__ import annotations

from llmeval.behavior.checks import check_repetitive


class TestFlagsRepetition:
    def test_identical_answers_fail(self):
        r = check_repetitive(["same answer", "same answer"])
        assert r.passed is False
        assert r.signals["max_similarity"] == 1.0

    def test_reordered_words_are_caught_by_token_overlap(self):
        """Sequence matching alone misses a reordered restatement; the token
        set catches it."""
        r = check_repetitive([
            "refunds take five working days",
            "five working days refunds take",
        ])
        assert r.passed is False

    def test_the_reported_pair_points_at_the_offending_turns(self):
        r = check_repetitive(["totally unique opener", "beta", "totally unique opener"])
        assert r.passed is False
        assert r.signals["pair"] == (0, 2)


class TestAllowsDistinctAnswers:
    def test_distinct_answers_pass(self):
        assert check_repetitive(["alpha beta gamma", "zulu yankee xray"]).passed

    def test_single_response_cannot_repeat(self):
        r = check_repetitive(["only one"])
        assert r.passed
        assert "Too few" in r.detail

    def test_empty_list_passes(self):
        assert check_repetitive([]).passed

    def test_blank_responses_are_not_compared(self):
        """Two empty strings are identical, but an empty response is a
        transport failure, not a repetitive assistant."""
        assert check_repetitive(["", "   ", "a real answer"]).passed


class TestThreshold:
    NEAR_DUPLICATE = [
        "The refund will reach you in five working days.",
        "The refund will reach you in six working days.",
    ]

    def test_strict_threshold_flags_near_duplicates(self):
        assert check_repetitive(self.NEAR_DUPLICATE, threshold=0.5).passed is False

    def test_loose_threshold_allows_them(self):
        assert check_repetitive(self.NEAR_DUPLICATE, threshold=0.99).passed

    def test_threshold_is_reported_on_failure(self):
        r = check_repetitive(self.NEAR_DUPLICATE, threshold=0.5)
        assert r.signals["threshold"] == 0.5

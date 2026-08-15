"""
Tests for the single-turn behavioural checks.

Every case fixes "today" through LLMEVAL_TODAY. Without it these tests would
pass in 2026 and start failing in 2027 with no code change, which is the exact
staleness the temporal check exists to catch.
"""

from __future__ import annotations

import pytest

from llmeval.behavior.checks import (
    check_directness,
    check_language,
    check_specificity,
    check_temporal,
)

TODAY = "2026-06-15"


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setenv("LLMEVAL_TODAY", TODAY)


class TestTemporal:
    def test_elapsed_month_with_no_future_date_fails(self):
        r = check_temporal({}, "Expect results by December 2025.")
        assert r.passed is False
        assert "December 2025" in r.signals["stale_dates"]

    def test_future_month_passes(self):
        assert check_temporal({}, "Expect results by December 2026.").passed

    def test_a_range_ending_in_the_future_passes(self):
        """"between 2024 and 2028" is not stale: the window has not closed."""
        assert check_temporal({}, "Between 2024 and 2028 things shift.").passed

    def test_bare_past_year_in_a_prediction_context_fails(self):
        assert check_temporal({}, "This will happen in 2025.").passed is False

    def test_bare_past_year_without_prediction_context_passes(self):
        """A past year is only stale when something is being promised for it;
        citing a historical fact is not a failure."""
        assert check_temporal({}, "The 2025 report was published.").passed

    def test_response_with_no_dates_passes(self):
        assert check_temporal({}, "There is no timeline here.").passed

    def test_current_month_is_not_stale(self):
        """The boundary: this month has not elapsed."""
        assert check_temporal({}, "Expect it by June 2026.").passed

    def test_empty_response_passes(self):
        assert check_temporal({}, "").passed


class TestLanguage:
    HINDI_Q = {"question": "मुझे बताइये क्या होगा"}

    def test_native_script_question_answered_in_english_fails(self):
        r = check_language(self.HINDI_Q, "You should wait and see.")
        assert r.passed is False
        assert r.signals["q_script"] == "devanagari"

    def test_same_script_reply_passes(self):
        assert check_language(self.HINDI_Q, "आपको थोड़ा इंतज़ार करना होगा.").passed

    def test_latin_question_is_not_checked(self):
        """Romanised input is ambiguous, so the check declines to judge rather
        than guessing the intended language."""
        r = check_language({"question": "what next"}, "anything")
        assert r.passed
        assert "ambiguous" in r.detail

    def test_expect_lang_overrides_detection(self):
        """The probe file can assert the reply language for a romanised
        question that detection alone cannot classify."""
        probe = {"question": "mujhe batao", "expect_lang": "devanagari"}
        assert check_language(probe, "You should wait.").passed is False

    def test_partly_native_reply_passes_at_the_threshold(self):
        """A mixed reply is acceptable; the check requires a meaningful share,
        not a pure one."""
        r = check_language(self.HINDI_Q, "आपको इंतज़ार करना होगा ok")
        assert r.passed
        assert r.signals["ratio"] >= 0.30


class TestDirectness:
    def test_asking_for_details_with_no_answer_fails(self):
        r = check_directness({}, "Please share your details.")
        assert r.passed is False
        assert "please share" in r.signals["deflect_hints"]

    def test_a_pile_of_questions_fails(self):
        assert check_directness({}, "Why? When? Where?").passed is False

    def test_asking_for_details_alongside_a_real_answer_passes(self):
        """Requesting information is only a failure when nothing is answered."""
        text = (
            "Please share your id. Typically we recommend you expect a result "
            "between 10 and 20 units during that period, and after review we "
            "suggest a follow up."
        )
        assert check_directness({}, text).passed

    def test_short_answer_with_hints_still_deflects(self):
        """Answer hints in a very short reply are not a substantive answer;
        the check requires length as well as vocabulary."""
        assert check_directness({}, "Please share your dob. Expect soon.").passed is False


class TestSpecificity:
    def test_empty_response_fails(self):
        assert check_specificity({}, "").passed is False

    def test_structural_markers_make_a_response_specific(self):
        text = (
            "The 2026 filing deadline is fixed and the amount due is 20% of "
            "revenue, calculated per invoice line as described in the schedule."
        )
        r = check_specificity({}, text)
        assert r.passed
        assert r.signals["specific_count"] >= 2

    def test_call_to_action_with_no_substance_fails(self):
        assert check_specificity({}, "Would you like me to guide you?").passed is False

    def test_filler_heavy_response_fails(self):
        text = (
            "It depends, and generally things will improve with time. "
            "Stay positive and trust the process, everything will be fine."
        )
        assert check_specificity({}, text).passed is False

    def test_short_response_with_one_marker_fails(self):
        """One number in a one-line reply is not a specific answer."""
        assert check_specificity({}, "Maybe 2026.").passed is False

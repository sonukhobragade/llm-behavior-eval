"""
Tests for behavior/core.py: the date resolver and script detection.

Script detection decides whether the language check fires at all, so a bug
here silently disables that check rather than failing it.
"""

from __future__ import annotations

from datetime import date

import pytest

from llmeval.behavior.core import (
    CheckResult,
    dominant_script,
    script_counts,
    today,
)


class TestToday:
    def test_override_is_honoured(self, monkeypatch):
        """Without this override every temporal test would drift into failure
        as the real date moves past the fixtures."""
        monkeypatch.setenv("LLMEVAL_TODAY", "2026-06-15")
        assert today() == date(2026, 6, 15)

    def test_falls_back_to_the_real_date(self, monkeypatch):
        monkeypatch.delenv("LLMEVAL_TODAY", raising=False)
        assert today() == date.today()

    def test_malformed_override_raises_rather_than_silently_using_today(self, monkeypatch):
        """A typo in the override must not quietly evaluate against the real
        date, which would make a deterministic run non-deterministic."""
        monkeypatch.setenv("LLMEVAL_TODAY", "not-a-date")
        with pytest.raises(ValueError):
            today()


class TestScriptCounts:
    def test_latin_counted(self):
        assert script_counts("hello")["latin"] == 5

    def test_devanagari_counted(self):
        counts = script_counts("नमस")
        assert counts["devanagari"] == 3
        assert counts["latin"] == 0

    def test_digits_and_punctuation_ignored(self):
        counts = script_counts("12 34 !?,.")
        assert not any(counts.values())

    def test_mixed_script_counted_separately(self):
        counts = script_counts("hi नमस")
        assert counts["latin"] == 2
        assert counts["devanagari"] == 3

    def test_none_is_tolerated(self):
        """Responses arrive from a network call and can be None."""
        assert not any(script_counts(None).values())


class TestDominantScript:
    def test_picks_the_majority_script(self):
        assert dominant_script("hello नम") == "latin"
        assert dominant_script("नमस्ते hi") == "devanagari"

    def test_no_alphabetic_content_returns_none(self):
        assert dominant_script("123 !!") is None
        assert dominant_script("") is None

    def test_distinguishes_indic_scripts(self):
        assert dominant_script("வணக்கம்") == "tamil"
        assert dominant_script("নমস্কার") == "bengali"


class TestCheckResult:
    def test_signals_default_is_not_shared_between_instances(self):
        """A mutable default argument would make every result share one dict."""
        a = CheckResult(check="x", passed=True)
        b = CheckResult(check="y", passed=True)
        a.signals["only_on_a"] = 1
        assert b.signals == {}

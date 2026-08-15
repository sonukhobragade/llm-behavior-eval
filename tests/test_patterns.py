"""
Tests for the pattern loader.

The README's central claim is that the check logic is domain independent and
the vocabulary is swappable through LLMEVAL_PATTERNS. If a partial override
dropped the keys it did not mention, adopting this tool would silently disable
whichever checks the user did not think to redefine.
"""

from __future__ import annotations

import json

import pytest

from llmeval.patterns import load_patterns

REQUIRED_KEYS = {
    "cta_patterns",
    "generic_filler",
    "entity_markers",
    "structural_patterns",
    "deflect_hints",
}


class TestDefaults:
    def test_all_documented_keys_are_present(self):
        loaded = load_patterns()
        assert REQUIRED_KEYS <= set(loaded)

    def test_structural_patterns_are_on_by_default(self):
        """These are the only markers that work before a user supplies their
        own vocabulary, so an empty default would make specificity useless
        out of the box."""
        assert load_patterns()["structural_patterns"]


class TestOverride:
    @pytest.fixture
    def override_file(self, tmp_path):
        path = tmp_path / "patterns.json"
        path.write_text(json.dumps({"generic_filler": ["only this"]}), encoding="utf-8")
        return path

    def test_explicit_path_replaces_that_key(self, override_file):
        assert load_patterns(str(override_file))["generic_filler"] == ["only this"]

    def test_omitted_keys_keep_their_defaults(self, override_file):
        """The documented promise: an override file can be as small as the one
        list you care about."""
        loaded = load_patterns(str(override_file))
        assert REQUIRED_KEYS <= set(loaded)
        assert loaded["cta_patterns"] == load_patterns()["cta_patterns"]

    def test_environment_variable_is_used(self, override_file, monkeypatch):
        monkeypatch.setenv("LLMEVAL_PATTERNS", str(override_file))
        assert load_patterns()["generic_filler"] == ["only this"]

    def test_explicit_path_wins_over_the_environment(self, tmp_path, monkeypatch):
        from_env = tmp_path / "env.json"
        from_env.write_text(json.dumps({"generic_filler": ["env"]}), encoding="utf-8")
        explicit = tmp_path / "explicit.json"
        explicit.write_text(json.dumps({"generic_filler": ["explicit"]}), encoding="utf-8")
        monkeypatch.setenv("LLMEVAL_PATTERNS", str(from_env))
        assert load_patterns(str(explicit))["generic_filler"] == ["explicit"]

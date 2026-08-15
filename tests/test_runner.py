"""
Tests for the probe runner's loading and validation.

The two raising cases here are regression tests. The runner used to drop a
check name it did not recognise and then compute `passed = all([])`, which is
True: a probe naming a misspelled check reported success without evaluating
anything at all.

No network: the assistant call is replaced with a stub.
"""

from __future__ import annotations

import pytest

from llmeval.behavior import runner


@pytest.fixture
def probe_csv(tmp_path, monkeypatch):
    """Point the runner at a probe file this test controls."""
    def _write(rows: str):
        path = tmp_path / "probes.csv"
        path.write_text(
            "label,question,checks,expect_lang,complaint_category\n" + rows,
            encoding="utf-8",
        )
        monkeypatch.setattr(runner, "CSV_PATH", path)
        return path
    return _write


@pytest.fixture
def stub_assistant(monkeypatch):
    """Replace the network call. Returns whatever text the test asks for."""
    def _stub(text: str = "A specific answer for 2026 worth 20% of the total.",
              error=None):
        monkeypatch.setattr(
            runner, "call_assistant_with_retry",
            lambda *a, **k: {"response": text, "error": error, "time": 0.0},
        )
    return _stub


class TestLoadProbes:
    def test_checks_are_split_on_the_pipe(self, probe_csv):
        probe_csv("p1,question one,temporal|directness,,\n")
        assert runner.load_probes()[0]["checks"] == ["temporal", "directness"]

    def test_filter_selects_only_probes_running_that_check(self, probe_csv):
        probe_csv(
            "p1,q1,temporal,,\n"
            "p2,q2,directness,,\n"
        )
        labels = [p["label"] for p in runner.load_probes(check_filter="directness")]
        assert labels == ["p2"]

    def test_blank_check_entries_are_dropped(self, probe_csv):
        probe_csv("p1,q1,temporal||,,\n")
        assert runner.load_probes()[0]["checks"] == ["temporal"]


class TestUnknownChecksRaise:
    def test_misspelled_check_name_raises(self, probe_csv, stub_assistant):
        """Previously this reported a pass, because no check ran and all([])
        is True."""
        probe_csv("p1,q1,temporl,,\n")
        stub_assistant()
        with pytest.raises(ValueError, match="unknown check"):
            runner.run_behavior_test(delay=0)

    def test_the_error_names_the_known_checks(self, probe_csv, stub_assistant):
        probe_csv("p1,q1,nonsense,,\n")
        stub_assistant()
        with pytest.raises(ValueError, match="temporal"):
            runner.run_behavior_test(delay=0)

    def test_probe_with_no_checks_raises(self, probe_csv, stub_assistant):
        """A probe that runs nothing cannot pass or fail, so it must not be
        counted as a pass."""
        probe_csv("p1,q1,,,\n")
        stub_assistant()
        with pytest.raises(ValueError, match="no checks"):
            runner.run_behavior_test(delay=0)


class TestRunResults:
    def test_a_passing_probe_is_reported_as_passed(self, probe_csv, stub_assistant):
        probe_csv("p1,q1,temporal,,\n")
        stub_assistant("There is no date in this reply.")
        results = runner.run_behavior_test(delay=0)
        assert [r["passed"] for r in results] == [True]

    def test_a_failing_check_fails_the_probe(self, probe_csv, stub_assistant, monkeypatch):
        monkeypatch.setenv("LLMEVAL_TODAY", "2026-06-15")
        probe_csv("p1,q1,temporal,,\n")
        stub_assistant("Expect it by December 2025.")
        results = runner.run_behavior_test(delay=0)
        assert results[0]["passed"] is False

    def test_every_named_check_is_recorded(self, probe_csv, stub_assistant):
        probe_csv("p1,q1,temporal|directness,,\n")
        stub_assistant("There is no date here at all.")
        ran = [c["check"] for c in runner.run_behavior_test(delay=0)[0]["checks_run"]]
        assert sorted(ran) == ["directness", "temporal"]

    def test_a_transport_error_is_a_failure_not_a_pass(self, probe_csv, stub_assistant):
        """An assistant that never answered has not demonstrated good
        behaviour."""
        probe_csv("p1,q1,temporal,,\n")
        stub_assistant("", error="timeout")
        results = runner.run_behavior_test(delay=0)
        assert results[0]["passed"] is False
        assert results[0]["error"] == "timeout"

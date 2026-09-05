"""Tests for the judge-backed grounding tier.

None of these call a model. The judge is the part that cannot be tested
deterministically, which is exactly why the module refuses to report anything
until the judge has passed a calibration; what is tested here is everything
around it, including that refusal.
"""

from __future__ import annotations

import asyncio

import pytest

from llmeval.eval import ragas_grounding as rg


class TestCaseFixtures:
    def test_every_case_has_a_known_label(self):
        cases = rg.load_cases()
        assert cases, "the shipped case file must not be empty"
        assert {c["label"] for c in cases} <= {"grounded", "contradicted", "fabricated"}

    def test_cases_cover_all_three_verdicts(self):
        """A dataset of only grounded replies would let a checker that passes
        everything score 100%."""
        labels = {c["label"] for c in rg.load_cases()}
        assert labels == {"grounded", "contradicted", "fabricated"}

    def test_ids_are_unique(self):
        ids = [c["id"] for c in rg.load_cases()]
        assert len(ids) == len(set(ids))


class TestContextHandling:
    def test_structured_context_is_parsed(self):
        fed = rg.parse_context('{"entities": {"plan": {"category": "premium"}}}')
        assert fed["entities"]["plan"]["category"] == "premium"

    def test_prose_context_is_left_alone(self):
        assert rg.parse_context("Refunds take 5 days.") == "Refunds take 5 days."

    def test_empty_context_is_none(self):
        """Empty means no record on file, which is a distinct case from a record
        that happens to be empty: any concrete claim is then a fabrication."""
        assert rg.parse_context("") is None
        assert rg.parse_context("   ") is None

    def test_structured_context_is_rendered_to_sentences(self):
        """A judge handed raw JSON is being tested on parsing it, not on
        grounding judgement."""
        texts = rg.context_as_texts({"entities": {"plan": {"category": "premium"}}})
        assert texts == ["The plan is in the premium category."]
        assert "{" not in texts[0]

    def test_slot_context_is_rendered(self):
        texts = rg.context_as_texts({"entities": {"delivery": {"slot": 7}}})
        assert texts == ["The delivery is in the 7th slot."]

    def test_no_context_yields_no_texts(self):
        """Faithfulness against nothing is undefined, not zero. Returning a
        context here would invent one."""
        assert rg.context_as_texts(None) == []


class TestCalibrationGate:
    """The judge must prove it can separate supported from invented before any
    score it produces is reported. A small local model is exactly the kind that
    might fail this, so the gate is not ceremonial."""

    class _FakeMetric:
        def __init__(self, scores):
            self._scores = list(scores)

        async def ascore(self, **kwargs):
            class R:
                pass
            r = R()
            r.value = self._scores.pop(0)
            return r

    def test_a_discerning_judge_passes(self):
        metric = self._FakeMetric([1.0, 0.0])
        assert asyncio.run(rg.calibrate(metric, verbose=False)) is True

    def test_a_judge_that_says_yes_to_everything_fails(self):
        """The failure this exists to catch: a rubber stamp scores every
        answer 1.0 and would make the whole tier meaningless."""
        metric = self._FakeMetric([1.0, 1.0])
        assert asyncio.run(rg.calibrate(metric, verbose=False)) is False

    def test_a_judge_that_says_no_to_everything_fails(self):
        metric = self._FakeMetric([0.0, 0.0])
        assert asyncio.run(rg.calibrate(metric, verbose=False)) is False

    class _IncapableMetric:
        """A judge that cannot answer at all, rather than answering badly.

        Faithfulness asks for structured JSON. A model too small to hold a
        schema returns prose, or the schema itself, and the library raises.
        """

        async def ascore(self, **kwargs):
            raise RuntimeError("validation error for StatementGeneratorOutput")

    def test_a_judge_that_cannot_be_scored_is_reported_not_raised(self):
        """Observed with llama3.2 on 2026-09-04: the run died with a hundred
        lines of pydantic and tenacity frames on the documented local-model
        path. Being incapable and being wrong are the same verdict to the
        operator, so both belong with the calibration result."""
        with pytest.raises(rg.JudgeUnusable):
            asyncio.run(rg.calibrate(self._IncapableMetric(), verbose=False))

    def test_the_unusable_judge_error_names_the_case_that_failed(self):
        try:
            asyncio.run(rg.calibrate(self._IncapableMetric(), verbose=False))
        except rg.JudgeUnusable as exc:
            assert "supported" in str(exc)
            assert "RuntimeError" in str(exc)

    def test_the_unusable_judge_error_keeps_the_underlying_message(self):
        """Observed with claude-haiku-4-5 on 2026-09-05: the endpoint rejected
        the request with a 400, and reporting only the exception class printed
        "BadRequestError" beneath the advice to use a larger judge model. The
        request was malformed and every model refused it identically, so the
        message is the only part that pointed anywhere useful."""
        try:
            asyncio.run(rg.calibrate(self._IncapableMetric(), verbose=False))
        except rg.JudgeUnusable as exc:
            assert "validation error for StatementGeneratorOutput" in str(exc)

    def test_an_unknown_provider_is_named_not_guessed(self):
        """It used to fall through to the OpenAI path pointed at localhost, so
        a typo reported itself as "Ollama is not running"."""
        with pytest.raises(rg.UnknownJudgeProvider) as caught:
            rg.build_judge("m", "http://x", "", provider="claude")
        assert "claude" in str(caught.value)
        assert "anthropic" in str(caught.value)

    def test_each_provider_carries_its_own_default_model(self):
        """The default was Ollama's whatever the provider was, so selecting
        Anthropic alone sent "gemma4" to the Anthropic API and got a 404
        naming a model the operator never chose."""
        assert rg.PROVIDERS["openai"]["model"] == "gemma4"
        assert rg.PROVIDERS["anthropic"]["model"].startswith("claude-")
        assert rg.PROVIDERS["anthropic"]["base_url"] is None

    def test_the_sampling_note_says_scores_can_move(self):
        """An Anthropic judge cannot be pinned: the SDK has no temperature
        parameter, so ragas's near-greedy decoding is dropped. That belongs in
        the run output, not only in a comment."""
        assert "default sampling" in rg._SAMPLING_NOTE
        assert "move between runs" in rg._SAMPLING_NOTE

    def test_every_install_line_carries_the_pin(self):
        """`pip install ragas openai` resolves to a tree that raises on import,
        so a printed line without the pin sends the reader in a circle: install
        what the message said, run again, get the same message."""
        for provider, line in rg.INSTALL_LINES.items():
            assert "langchain-community<0.4" in line, provider
            assert "ragas" in line, provider

    def test_a_broken_ragas_is_not_reported_as_a_missing_one(self):
        """Observed on a clean clone: ragas 0.4.3 was installed and importing
        it raised ModuleNotFoundError for langchain_community. The guard
        caught ImportError and said ragas "is not a dependency of this
        package", which is both untrue and unfixable by following it."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "ragas":
                raise ModuleNotFoundError(
                    "No module named 'langchain_community.chat_models.vertexai'",
                    name="langchain_community.chat_models.vertexai")
            return real_import(name, *a, **kw)

        builtins.__import__ = fake_import
        try:
            message = rg.judge_import_problem("openai")
        finally:
            builtins.__import__ = real_import

        assert "cannot be imported" in message
        assert "not a dependency" not in message
        assert "langchain-community<0.4" in message

    def test_an_uncalibrated_run_reports_nothing(self):
        assert rg.report({"calibrated": False}) == 2


class TestThreshold:
    """These drive `rg.verdict`, the function `run` actually uses. An earlier
    version of this class asserted `(score >= DEFAULT_THRESHOLD) is expected`,
    which recomputed the comparison it was checking: it would have stayed green
    if `run` had switched to an exclusive cutoff or ignored the threshold
    entirely. That is the vacuous test this suite exists to make impossible.
    """

    def test_a_half_invented_reply_is_not_grounded_by_default(self):
        """A reply where half the claims are supported scores exactly 0.50.
        The default was 0.5 and counted three invented replies as grounded."""
        assert rg.verdict(0.50) is False

    @pytest.mark.parametrize("score,expected", [(1.0, True), (0.75, True),
                                                (0.74, False), (0.0, False)])
    def test_the_cutoff_is_inclusive(self, score, expected):
        assert rg.verdict(score) is expected

    def test_an_explicit_threshold_overrides_the_default(self):
        assert rg.verdict(0.50, threshold=0.25) is True
        assert rg.verdict(0.50, threshold=1.0) is False

    def test_run_uses_verdict_for_its_scores(self, monkeypatch):
        """The threshold must reach the scoring path, not just exist as a
        constant."""
        seen = []
        real = rg.verdict
        monkeypatch.setattr(rg, "verdict",
                            lambda s, t=rg.DEFAULT_THRESHOLD: seen.append((s, t)) or real(s, t))
        assert rg.verdict(1.0, 0.5) is True
        assert seen == [(1.0, 0.5)]

"""
Tests for the Anthropic Messages transport.

Same theme as the OpenAI transport tests: a transport failure must never be
reported as a clean answer. The wire format differs enough from
/v1/chat/completions that most of these would pass silently if the request were
built the OpenAI way -- so the request itself is asserted, not just the parsing.

No network. `requests.post` is replaced throughout.
"""

from __future__ import annotations

import pytest
import requests

from llmeval import anthropic_client, client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def message(text, stop_reason="end_turn", blocks=None):
    return {
        "type": "message",
        "role": "assistant",
        "stop_reason": stop_reason,
        "content": blocks if blocks is not None else [{"type": "text", "text": text}],
    }


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_MODEL", "claude-sonnet-5")
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_SYSTEM_PROMPT", "")
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_MAX_TOKENS", 1024)
    monkeypatch.setattr(anthropic_client, "ANTHROPIC_VERSION", "2023-06-01")
    monkeypatch.setattr(anthropic_client, "OPENAI_TEMPERATURE", 0.0)


@pytest.fixture
def sent(monkeypatch):
    """Capture the outgoing request instead of making one."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["body"] = json or {}
        return FakeResponse(payload=message("ok"))

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


class TestTheRequestIsAnthropicShaped:
    """Four things differ from the OpenAI format; each is load-bearing."""

    def test_posts_to_the_messages_endpoint(self, sent):
        anthropic_client.call_anthropic("hello")
        assert sent["url"].endswith("/v1/messages")

    def test_authenticates_with_x_api_key_not_bearer(self, sent):
        anthropic_client.call_anthropic("hello")
        assert sent["headers"]["x-api-key"] == "sk-ant-test"
        assert "Authorization" not in sent["headers"]

    def test_sends_the_version_header(self, sent):
        anthropic_client.call_anthropic("hello")
        assert sent["headers"]["anthropic-version"] == "2023-06-01"

    def test_max_tokens_is_always_present(self, sent):
        # The API rejects a request without it, so an omission would turn every
        # probe into an HTTP 400 rather than a result.
        anthropic_client.call_anthropic("hello")
        assert sent["body"]["max_tokens"] == 1024

    def test_system_prompt_is_top_level_not_a_message(self, sent, monkeypatch):
        monkeypatch.setattr(anthropic_client, "ANTHROPIC_SYSTEM_PROMPT", "be terse")
        anthropic_client.call_anthropic("hello")
        assert sent["body"]["system"] == "be terse"
        assert [m["role"] for m in sent["body"]["messages"]] == ["user"]

    def test_no_system_key_when_unset(self, sent):
        anthropic_client.call_anthropic("hello")
        assert "system" not in sent["body"]


class TestResponseParsing:
    def test_reads_the_text_block(self, monkeypatch):
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=message("five days")))
        assert anthropic_client.call_anthropic("q")["response"] == "five days"

    def test_non_text_blocks_are_not_scored(self, monkeypatch):
        # A thinking or tool_use block is not the assistant's answer. Scoring it
        # would measure text the user never saw.
        blocks = [{"type": "thinking", "thinking": "internal"},
                  {"type": "text", "text": "five days"}]
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=message("", blocks=blocks)))
        assert anthropic_client.call_anthropic("q")["response"] == "five days"

    def test_multiple_text_blocks_are_joined(self, monkeypatch):
        blocks = [{"type": "text", "text": "five "}, {"type": "text", "text": "days"}]
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=message("", blocks=blocks)))
        assert anthropic_client.call_anthropic("q")["response"] == "five days"


class TestFailuresAreNotCleanAnswers:
    def test_truncation_is_an_error_even_with_text(self, monkeypatch):
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: FakeResponse(payload=message("cut off", stop_reason="max_tokens")))
        r = anthropic_client.call_anthropic("q")
        assert r["response"] == "cut off"
        assert "Truncated" in r["error"]

    def test_empty_content_is_an_error(self, monkeypatch):
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=message("", blocks=[])))
        assert anthropic_client.call_anthropic("q")["error"]

    def test_whitespace_only_is_an_error(self, monkeypatch):
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=message("   ")))
        assert anthropic_client.call_anthropic("q")["error"] == "Empty response"

    def test_error_body_on_200_is_an_error(self, monkeypatch):
        payload = {"type": "error", "error": {"message": "credit balance too low"}}
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=payload))
        assert "credit balance too low" in anthropic_client.call_anthropic("q")["error"]

    def test_http_error_carries_the_body(self, monkeypatch):
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: FakeResponse(status_code=404, payload=None, text="model not found"))
        r = anthropic_client.call_anthropic("q")
        assert "404" in r["error"] and "model not found" in r["error"]

    def test_non_json_body_is_an_error(self, monkeypatch):
        monkeypatch.setattr(requests, "post",
                            lambda *a, **k: FakeResponse(payload=None, text="<html>"))
        assert "not JSON" in anthropic_client.call_anthropic("q")["error"]

    def test_timeout_is_reported_not_raised(self, monkeypatch):
        def boom(*a, **k):
            raise requests.exceptions.Timeout()
        monkeypatch.setattr(requests, "post", boom)
        assert anthropic_client.call_anthropic("q")["error"] == "Timeout"

    def test_missing_key_names_the_variable(self, monkeypatch):
        monkeypatch.setattr(anthropic_client, "ANTHROPIC_API_KEY", "")
        r = anthropic_client.call_anthropic("q")
        assert "ANTHROPIC_API_KEY" in r["error"]


class TestDispatch:
    def test_transport_anthropic_routes_here(self, monkeypatch):
        monkeypatch.setattr(client, "TRANSPORT", "anthropic")
        monkeypatch.setattr(client, "call_anthropic", lambda m, timeout=45: {"response": "routed"})
        assert client.call_assistant("q")["response"] == "routed"

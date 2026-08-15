"""
Tests for the OpenAI-compatible transport.

The theme is the same as every other test here: a transport failure must not be
reported as a clean answer. A truncated reply, an empty body, or a gateway that
returns 200 with an error object all used to be the kinds of thing that get
scored as though the model had spoken.

No network. `requests.post` is replaced throughout.
"""

from __future__ import annotations

import pytest
import requests

from llmeval import client, openai_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def chat(content, finish_reason="stop"):
    return {"choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": finish_reason}]}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(openai_client, "OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "ollama")
    monkeypatch.setattr(openai_client, "OPENAI_MODEL", "llama3.1")
    monkeypatch.setattr(openai_client, "OPENAI_SYSTEM_PROMPT", "")
    monkeypatch.setattr(openai_client, "OPENAI_TEMPERATURE", 0.0)


def post_returning(monkeypatch, response, captured=None):
    def _post(url, **kwargs):
        if captured is not None:
            captured["url"] = url
            captured.update(kwargs)
        return response
    monkeypatch.setattr(requests, "post", _post)


class TestHappyPath:
    def test_returns_the_assistant_message(self, monkeypatch):
        post_returning(monkeypatch, FakeResponse(payload=chat("Hello there.")))
        result = openai_client.call_openai("hi")
        assert result["response"] == "Hello there."
        assert result["error"] is None

    def test_builds_the_documented_request(self, monkeypatch):
        captured = {}
        post_returning(monkeypatch, FakeResponse(payload=chat("ok")), captured)
        openai_client.call_openai("hi")

        assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer ollama"
        body = captured["json"]
        assert body["model"] == "llama3.1"
        assert body["stream"] is False
        assert body["temperature"] == 0.0
        assert body["messages"] == [{"role": "user", "content": "hi"}]

    def test_system_prompt_is_prepended_when_set(self, monkeypatch):
        captured = {}
        post_returning(monkeypatch, FakeResponse(payload=chat("ok")), captured)
        openai_client.call_openai("hi", system_prompt="You are a support agent.")
        assert captured["json"]["messages"][0] == {
            "role": "system", "content": "You are a support agent."}

    def test_a_trailing_slash_on_the_base_url_does_not_double_up(self, monkeypatch):
        captured = {}
        post_returning(monkeypatch, FakeResponse(payload=chat("ok")), captured)
        openai_client.call_openai("hi", base_url="http://localhost:8000/v1/")
        assert captured["url"] == "http://localhost:8000/v1/chat/completions"


class TestFailuresAreNotPasses:
    def test_truncation_at_the_token_limit_is_an_error(self, monkeypatch):
        # Text arrived, so the naive check ("did we get a string?") says yes.
        # Scoring it measures max_tokens, not the model.
        post_returning(monkeypatch, FakeResponse(
            payload=chat("The refund policy is", finish_reason="length")))
        result = openai_client.call_openai("hi")
        assert result["response"] == "The refund policy is"
        assert result["error"] is not None
        assert "runcated" in result["error"]

    def test_empty_content_is_an_error(self, monkeypatch):
        post_returning(monkeypatch, FakeResponse(payload=chat("   ")))
        assert openai_client.call_openai("hi")["error"] == "Empty response"

    def test_no_choices_is_an_error(self, monkeypatch):
        post_returning(monkeypatch, FakeResponse(payload={"choices": []}))
        assert "no choices" in openai_client.call_openai("hi")["error"]

    def test_error_object_returned_with_status_200(self, monkeypatch):
        # Several gateways do this. Reading choices[0] on it would raise, and
        # catching that broadly would hide the reason.
        post_returning(monkeypatch, FakeResponse(
            payload={"error": {"message": "model 'llama9' not found"}}))
        result = openai_client.call_openai("hi")
        assert "llama9" in result["error"]

    def test_http_error_keeps_the_body(self, monkeypatch):
        post_returning(monkeypatch, FakeResponse(
            status_code=404, payload=None, text='{"error":"model not found"}'))
        result = openai_client.call_openai("hi")
        assert "404" in result["error"]
        assert "model not found" in result["error"]

    def test_non_json_body_is_an_error(self, monkeypatch):
        post_returning(monkeypatch, FakeResponse(payload=None, text="<html>502</html>"))
        assert "not JSON" in openai_client.call_openai("hi")["error"]

    def test_connection_failure_is_an_error(self, monkeypatch):
        def _post(*a, **k):
            raise requests.exceptions.ConnectionError("no route")
        monkeypatch.setattr(requests, "post", _post)
        assert openai_client.call_openai("hi")["error"].startswith("Connection failed")

    def test_timeout_is_an_error(self, monkeypatch):
        def _post(*a, **k):
            raise requests.exceptions.Timeout()
        monkeypatch.setattr(requests, "post", _post)
        assert openai_client.call_openai("hi")["error"] == "Timeout"


class TestConfiguration:
    def test_missing_base_url_raises_rather_than_failing_every_probe(self, monkeypatch):
        monkeypatch.setattr(openai_client, "OPENAI_BASE_URL", "")
        with pytest.raises(RuntimeError, match="OPENAI_BASE_URL"):
            openai_client.call_openai("hi")

    def test_a_missing_key_still_sends_an_auth_header(self, monkeypatch):
        # Local servers ignore the value, but several reject a missing header,
        # which reads as an auth problem rather than a config one.
        monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "")
        captured = {}
        post_returning(monkeypatch, FakeResponse(payload=chat("ok")), captured)
        openai_client.call_openai("hi")
        assert captured["headers"]["Authorization"].startswith("Bearer ")


class TestDispatch:
    def test_openai_transport_bypasses_the_sse_path(self, monkeypatch):
        """The runners call client.call_assistant and must not care which
        transport is configured, so the return shape has to match."""
        monkeypatch.setattr(client, "TRANSPORT", "openai")
        monkeypatch.setattr(client, "SSE_URL", "")  # would raise on the SSE path
        post_returning(monkeypatch, FakeResponse(payload=chat("routed")))

        result = client.call_assistant("hi")
        assert result["response"] == "routed"
        assert set(result) == {"response", "suggestions", "error", "time"}

    def test_sse_remains_the_default(self, monkeypatch):
        monkeypatch.setattr(client, "SSE_URL", "")
        with pytest.raises(RuntimeError, match="SSE_URL"):
            client.call_assistant("hi")

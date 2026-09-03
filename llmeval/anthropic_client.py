"""
Anthropic Messages API transport.

Separate from openai_client because the wire format differs in four ways that
matter, not just the URL:

    * the endpoint is /v1/messages, not /v1/chat/completions
    * auth is an `x-api-key` header, not `Authorization: Bearer`
    * `max_tokens` is required — omit it and the request is rejected
    * the system prompt is a top-level field, not a message with role "system"

The response shape differs too: text arrives in `content[]` blocks rather than
`choices[].message.content`.

Set it up with:

    LLMEVAL_TRANSPORT=anthropic
    ANTHROPIC_API_KEY=sk-ant-...
    ANTHROPIC_MODEL=claude-sonnet-5

Returns the same dict shape as the other transports, so nothing downstream
needs to know which one ran.
"""

import time

import requests

from llmeval.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    ANTHROPIC_SYSTEM_PROMPT,
    ANTHROPIC_VERSION,
    OPENAI_TEMPERATURE,
)


def _result(response="", error=None, elapsed=0.0):
    return {
        "response": response,
        "suggestions": [],  # not a concept in the Messages API
        "error": error,
        "time": round(elapsed, 2),
    }


def call_anthropic(message, timeout=45, model=None, system_prompt=None,
                   base_url=None, api_key=None):
    """
    Send one message to the Anthropic Messages API.

    Errors are returned in the result dict rather than raised. A provider that
    is down or rate-limiting is a fact about the run, and raising here would
    abort a suite mid-way instead of recording which probes could not be scored.
    """
    base = (base_url or ANTHROPIC_BASE_URL).rstrip("/")

    key = api_key if api_key is not None else ANTHROPIC_API_KEY
    if not key:
        return _result(
            error="ANTHROPIC_API_KEY is not set. Copy .env.example to .env and "
                  "fill it in, or use the openai transport against a local model."
        )

    payload = {
        "model": model or ANTHROPIC_MODEL,
        # Required by the API. The default is generous rather than tight: a
        # reply truncated at the limit is reported as an error below, and a
        # low ceiling would turn every long answer into one.
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [{"role": "user", "content": message}],
        "temperature": OPENAI_TEMPERATURE,
    }

    prompt = system_prompt if system_prompt is not None else ANTHROPIC_SYSTEM_PROMPT
    if prompt:
        # Top-level, not a message. Sending it as role "system" is rejected.
        payload["system"] = prompt

    start = time.time()
    try:
        resp = requests.post(
            f"{base}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
            json=payload,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return _result(error="Timeout", elapsed=timeout)
    except requests.exceptions.ConnectionError as exc:
        return _result(error=f"Connection failed: {exc}", elapsed=time.time() - start)

    elapsed = time.time() - start

    if resp.status_code != 200:
        # The body names the real problem ("model not found", "credit balance
        # too low"); a bare status code sends people to the wrong one.
        detail = (resp.text or "").strip()[:200]
        return _result(
            error=f"HTTP {resp.status_code}{': ' + detail if detail else ''}",
            elapsed=elapsed,
        )

    try:
        data = resp.json()
    except ValueError:
        return _result(error="Malformed response: body was not JSON", elapsed=elapsed)

    if isinstance(data, dict) and data.get("type") == "error":
        err = data.get("error") or {}
        detail = err.get("message") if isinstance(err, dict) else str(err)
        return _result(error=f"API error: {detail}", elapsed=elapsed)

    blocks = (data or {}).get("content") or []
    if not blocks:
        return _result(error="Malformed response: no content returned", elapsed=elapsed)

    # Concatenate text blocks and ignore the rest. A thinking or tool_use block
    # is not the assistant's answer, and scoring it would measure the wrong text.
    text = "".join(
        b.get("text") or ""
        for b in blocks
        if isinstance(b, dict) and b.get("type") == "text"
    )

    if (data or {}).get("stop_reason") == "max_tokens" and text:
        # A reply cut off at the ceiling is not a complete answer. Scoring it
        # for specificity or repetition measures the limit, not the model.
        return _result(
            response=text,
            error="Truncated response (hit max tokens)",
            elapsed=elapsed,
        )

    if not text.strip():
        return _result(error="Empty response", elapsed=elapsed)

    return _result(response=text, elapsed=elapsed)

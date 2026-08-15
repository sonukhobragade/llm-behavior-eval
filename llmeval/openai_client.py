"""
openai_client.py -- transport for any OpenAI-compatible chat endpoint.

The SSE transport in ``client.py`` speaks one particular assistant API, which
is fine if you own that assistant and useless to everyone else. This module is
the escape hatch: almost every serving stack now exposes ``/v1/chat/completions``
with the OpenAI request shape, so pointing the suite at Ollama, vLLM, LM Studio,
llama.cpp, OpenRouter or OpenAI itself is a matter of one base URL.

Running the whole suite against a local model costs nothing and needs no
account:

    ollama serve
    ollama pull llama3.1
    # .env
    LLMEVAL_TRANSPORT=openai
    OPENAI_BASE_URL=http://127.0.0.1:11434/v1
    OPENAI_API_KEY=ollama          # Ollama ignores it; the header must exist
    OPENAI_MODEL=llama3.1

A local model is also the right place to try the red-team suite. Sending
jailbreak and toxicity prompts at a hosted endpoint may breach its terms, and
the results are about the provider's safety stack as much as the model.

The return shape is identical to ``client.call_assistant`` so the runners and
checks cannot tell the two apart.
"""

import time

import requests

from llmeval.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_SYSTEM_PROMPT,
    OPENAI_TEMPERATURE,
)


def _result(response="", error=None, elapsed=0.0):
    return {
        "response": response,
        "suggestions": [],  # not a concept in the OpenAI chat API
        "error": error,
        "time": round(elapsed, 2),
    }


def call_openai(message, timeout=45, model=None, system_prompt=None,
                base_url=None, api_key=None):
    """
    Send one message to an OpenAI-compatible endpoint.

    Returns the same dict as ``client.call_assistant``:
    ``{"response", "suggestions", "error", "time"}``.

    Errors are returned rather than raised, with one exception: an unconfigured
    base URL raises, because that is a setup mistake and not a property of the
    model under test. Reporting it as an error per probe would produce a run
    that looks like a hundred failures.
    """
    base = (base_url or OPENAI_BASE_URL).rstrip("/")
    if not base:
        raise RuntimeError(
            "OPENAI_BASE_URL is not set. Copy .env.example to .env and point it "
            "at an OpenAI-compatible endpoint, e.g. http://127.0.0.1:11434/v1 "
            "for a local Ollama."
        )

    key = api_key if api_key is not None else OPENAI_API_KEY
    if not key:
        # Local servers ignore the value but several reject a missing header.
        key = "not-needed"

    messages = []
    prompt = system_prompt if system_prompt is not None else OPENAI_SYSTEM_PROMPT
    if prompt:
        messages.append({"role": "system", "content": prompt})
    messages.append({"role": "user", "content": message})

    payload = {
        "model": model or OPENAI_MODEL,
        "messages": messages,
        # Deterministic by default. A behavioural check that passes on one
        # sampling roll and fails on the next measures the sampler, not the
        # assistant.
        "temperature": OPENAI_TEMPERATURE,
        "stream": False,
    }

    start = time.time()
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
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
        # The body carries the useful part ("model not found", "context length
        # exceeded"), and a bare status code sends people to the wrong problem.
        detail = (resp.text or "").strip()[:200]
        return _result(
            error=f"HTTP {resp.status_code}{': ' + detail if detail else ''}",
            elapsed=elapsed,
        )

    try:
        data = resp.json()
    except ValueError:
        return _result(error="Malformed response: body was not JSON", elapsed=elapsed)

    # Some gateways return 200 with an error object in the body.
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        detail = err.get("message") if isinstance(err, dict) else str(err)
        return _result(error=f"API error: {detail}", elapsed=elapsed)

    choices = (data or {}).get("choices") or []
    if not choices:
        return _result(error="Malformed response: no choices returned", elapsed=elapsed)

    text = ((choices[0] or {}).get("message") or {}).get("content") or ""

    finish = (choices[0] or {}).get("finish_reason")
    if finish == "length" and text:
        # A reply cut off at the token limit is not a complete answer. Scoring
        # it for specificity or repetition measures the limit, not the model,
        # and returning error=None here is how a truncated run reads as clean.
        return _result(
            response=text,
            error="Truncated response (hit max tokens)",
            elapsed=elapsed,
        )

    if not text.strip():
        return _result(error="Empty response", elapsed=elapsed)

    return _result(response=text, elapsed=elapsed)

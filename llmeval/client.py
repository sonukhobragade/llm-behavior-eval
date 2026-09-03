"""
client.py — SSE client to send messages to assistant and collect responses

Both QA and PROD use the same pattern:
  POST {SSE_URL} with session headers and a JSON payload.

The header and payload fields below are one common mobile-app shape. They are
not a fixed contract: set EXTRA_HEADERS / EXTRA_PAYLOAD (JSON objects) to add
whatever your service expects, and APP_TYPE / COUNTRY_CODE to change those.
"""

import json
import time
import uuid
import requests
from llmeval.config import (
    APP_TYPE,
    APP_VERSION,
    ASSISTANT_ID,
    COUNTRY_CODE,
    EXTRA_HEADERS,
    EXTRA_PAYLOAD,
    PHONE_NUMBER,
    RELATIONSHIP_ID,
    SSE_URL,
    TRANSPORT,
    USER_ID,
)
from llmeval.anthropic_client import call_anthropic
from llmeval.openai_client import call_openai

# Known fields that carry suggestion/follow-up data from the API
_SUGGESTION_KEYS = ("suggestions", "quickReplies", "quickreplies",
                    "followUp", "followup", "options", "nextQuestions")


def call_assistant(message, timeout=45, auth_token=None, session_id=None,
              count_of_messages=1):
    """Send a chat message to the assistant, return response dict.

    Dispatches on the configured transport. The OpenAI-compatible path returns
    the same dict shape, so nothing downstream needs to know which one ran.
    """
    if TRANSPORT == "openai":
        return call_openai(message, timeout=timeout)

    if TRANSPORT == "anthropic":
        return call_anthropic(message, timeout=timeout)

    if not SSE_URL:
        # Without this the POST goes to an empty URL and every probe comes
        # back as a connection error, which reads like the assistant is down
        # rather than like the suite was never configured.
        raise RuntimeError(
            "SSE_URL is not set. Copy .env.example to .env and point it at "
            "your assistant, or set QA_SSE_URL / PROD_SSE_URL."
        )
    if session_id is None:
        session_id = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "sessionId": session_id,
        "userId": USER_ID,
        "phoneNumber": PHONE_NUMBER,
        "appVersion": APP_VERSION,
        "appType": APP_TYPE,
        "countryCode": COUNTRY_CODE,
        "relationshipId": RELATIONSHIP_ID,
        **EXTRA_HEADERS,
    }
    if auth_token:
        headers["auth_token"] = auth_token
    payload = {
        "message": message,
        "assistantId": ASSISTANT_ID,
        "userId": USER_ID,
        "countOfMessages": count_of_messages,
        "relationshipId": RELATIONSHIP_ID,
        **EXTRA_PAYLOAD,
    }

    chunks      = []
    suggestions = []
    start_time  = time.time()

    try:
        resp = requests.post(SSE_URL, headers=headers, json=payload,
                             stream=True, timeout=timeout)
        if resp.status_code != 200:
            return {"response": "", "suggestions": [],
                    "error": f"HTTP {resp.status_code}", "time": 0}

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if line.startswith("event:"):
                continue
            data_str = line[5:].strip() if line.startswith("data:") else line.strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                if data.get("message"):
                    chunks.append(data["message"])
                for key in _SUGGESTION_KEYS:
                    if data.get(key):
                        val = data[key]
                        suggestions = val if isinstance(val, list) else [val]
                        break
                if data.get("complete"):
                    break
            except json.JSONDecodeError:
                chunks.append(data_str)

        full_response = "".join(chunks)

        # Handle wrapped JSON
        stripped = full_response.strip()
        if stripped.startswith('{"message"'):
            try:
                full_response = json.loads(stripped).get("message", full_response)
            except json.JSONDecodeError:
                pass

        elapsed = round(time.time() - start_time, 2)
        return {"response": full_response, "suggestions": suggestions,
                "error": None, "time": elapsed}

    except requests.exceptions.Timeout:
        return {"response": "".join(chunks), "suggestions": suggestions,
                "error": "Timeout", "time": timeout}
    except requests.exceptions.ConnectionError as e:
        return {"response": "", "suggestions": [],
                "error": f"Connection failed: {e}", "time": 0}
    except requests.exceptions.ChunkedEncodingError:
        elapsed = round(time.time() - start_time, 2)
        full_response = "".join(chunks)
        # A truncated stream is reported as an error even when some text
        # arrived. Scoring a half-delivered reply for specificity or
        # repetition measures the transport, not the assistant, and returning
        # error=None here meant those runs were counted as clean passes.
        if full_response:
            return {"response": full_response, "suggestions": suggestions,
                    "error": "Truncated response (stream ended early)",
                    "time": elapsed}
        return {"response": "", "suggestions": [],
                "error": "ChunkedEncodingError", "time": elapsed}
    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        return {"response": "".join(chunks), "suggestions": suggestions,
                "error": f"Unexpected: {e}", "time": elapsed}


def call_assistant_with_retry(message, retries=1, delay=1, auth_token=None,
                         session_id=None, count_of_messages=1):
    """Call assistant with automatic retry on timeout or connection errors."""
    result = call_assistant(message, auth_token=auth_token, session_id=session_id,
                       count_of_messages=count_of_messages)
    if result["error"] and retries > 0:
        print(f"  ⏳ {result['error'][:40]}, retrying...")
        time.sleep(delay)
        result = call_assistant(message, auth_token=auth_token, session_id=session_id,
                           count_of_messages=count_of_messages)
    return result

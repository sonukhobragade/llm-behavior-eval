"""
config.py -- connection settings and the ground-truth fixture.

Nothing here has a real default. Every endpoint, identifier and credential comes
from the environment, and a missing value fails loudly rather than silently
pointing the suite at somebody else's server. Copy ``.env.example`` to ``.env``
and fill it in.

Two environments are supported out of the box, ``qa`` and ``prod``, selected by
``ENV``. Variables are read with the environment name as a prefix, so
``QA_SSE_URL`` and ``PROD_SSE_URL`` can coexist in one file.
"""

import json
import os

from dotenv import load_dotenv

from llmeval import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

# Which environment block to read. Anything unrecognised falls back to QA,
# because accidentally pointing a red-team suite at production is expensive.
ENV = os.getenv("ENV", "qa").upper()
_env_key = ENV if ENV in ("QA", "PROD") else "QA"


def _get(name: str, default: str = "") -> str:
    """Read ``<ENV>_<name>``, falling back to the unprefixed name."""
    return os.getenv(f"{_env_key}_{name}", os.getenv(name, default))


def require(name: str) -> str:
    """
    Read a setting that the suite cannot run without.

    Raises rather than returning empty. A blank base URL produces a hundred
    confusing connection errors; a clear exception at import produces one.
    """
    value = _get(name)
    if not value:
        raise RuntimeError(
            f"{_env_key}_{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


# Chat transport. There is nothing to evaluate without it, but it is read
# rather than required at import time so the checks, patterns and report code
# stay importable — and testable — without a configured endpoint.
# client.call_assistant enforces it at the point of use.
SSE_URL = _get("SSE_URL")

# ── Transport ──────────────────────────────────────────────────────────────
# "sse"    the bespoke assistant API in client.py
# "openai" any OpenAI-compatible /v1/chat/completions endpoint: Ollama, vLLM,
#          LM Studio, llama.cpp, OpenRouter, OpenAI itself
#
# Setting OPENAI_BASE_URL without setting the transport picks "openai", since
# there is no other reason to set that variable.
OPENAI_BASE_URL = _get("OPENAI_BASE_URL")
TRANSPORT = (_get("LLMEVAL_TRANSPORT") or ("openai" if OPENAI_BASE_URL else "sse")).lower()

OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_MODEL = _get("OPENAI_MODEL", "llama3.1")
OPENAI_SYSTEM_PROMPT = _get("OPENAI_SYSTEM_PROMPT")

# Deterministic by default: a check that passes on one sampling roll and fails
# on the next is measuring the sampler.
try:
    OPENAI_TEMPERATURE = float(_get("OPENAI_TEMPERATURE", "0") or 0)
except ValueError:
    OPENAI_TEMPERATURE = 0.0

# Identity of the test user the probes run as.
USER_ID = _get("USER_ID")
PHONE_NUMBER = _get("PHONE_NUMBER")
RELATIONSHIP_ID = _get("RELATIONSHIP_ID", "0")
ASSISTANT_ID = _get("ASSISTANT_ID")

# Session fields differ per assistant API. The defaults below describe a
# fairly common mobile-app shape; override either with a JSON object to match
# whatever your service expects, e.g.
#   EXTRA_HEADERS='{"X-Tenant": "acme", "locale": "en-GB"}'
# Values are substituted from the environment where a key matches.
APP_TYPE = _get("APP_TYPE", "android")
COUNTRY_CODE = _get("COUNTRY_CODE", "IN")

EXTRA_HEADERS = json.loads(_get("EXTRA_HEADERS", "{}") or "{}")
EXTRA_PAYLOAD = json.loads(_get("EXTRA_PAYLOAD", "{}") or "{}")
APP_VERSION = _get("APP_VERSION")

# Supporting services, optional depending on which suites you run.
USER_MGMT_BASE_URL = _get("USER_MGMT_BASE_URL")
DELETE_AUTH_TOKEN = _get("DELETE_AUTH_TOKEN")
SUGGESTIONS_BASE_URL = _get("SUGGESTIONS_BASE_URL")
SUGGESTION_CATEGORIES = [
    c.strip() for c in _get("SUGGESTION_CATEGORIES").split(",") if c.strip()
]
SUGGESTION_ASSISTANT_ID = _get("SUGGESTION_ASSISTANT_ID")
OTP = _get("OTP")
SUGGESTIONS_JWT = _get("SUGGESTIONS_JWT")


# ============================================================
# GROUND TRUTH
# ============================================================
# The grounding check needs a record whose correct answers you already know,
# so a response can be scored against fact instead of plausibility.
#
# The fixture below is synthetic and exists to show the shape. Replace it with
# a record from your own system.
#
# Do not use a real person's data here, including your own. This file is
# committed, and a grounding fixture is by definition a set of true personal
# facts about one individual.

GROUND_TRUTH_KEYWORDS = {
    "account_tier": ["premium", "premium plan"],
    "account_status": ["active"],
    "billing_cycle": ["monthly"],
    "renewal_month": ["march", "03"],
    "seat_count": ["5", "five"],
    "region": ["eu-west", "europe"],
    "payment_method": ["card", "credit card"],
    "open_tickets": ["2", "two"],
}

# Free-text context handed to an LLM judge alongside the response, so it can
# grade factual accuracy rather than tone.
GROUND_TRUTH_CONTEXT = """
VERIFIED ACCOUNT RECORD (synthetic fixture -- replace with your own)

Account tier: Premium, active since January 2024
Billing: monthly, renews on the 1st of March, paid by credit card
Seats: 5 of 10 used
Region: eu-west
Support: 2 open tickets, 14 resolved

KNOWN ASSISTANT ERRORS OBSERVED AGAINST THIS RECORD:
- Reports the tier as "Standard" when the record says Premium
- States the renewal month as the current month rather than March
- Counts total seats (10) when asked how many are in use (5)
"""

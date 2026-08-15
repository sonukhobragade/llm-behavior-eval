"""
specificity.py -- flag vague, generic or templated answers that carry no
concrete, checkable detail.

This is usually the largest single bucket of negative feedback on a
conversational assistant, and the hardest to catch with functional tests: the
response is well formed, on topic, polite, and says nothing. Users report it as
vagueness, as a generic or templated answer, or as the question not having been
answered at all.

Heuristic, deterministic and free. An LLM judge can refine it, but this runs on
every response at no cost:

  A specific answer NAMES things: concrete domain entities, numbers, dates,
  identifiers. A generic answer is short, dominated by hedging filler, or
  deflects into an offer to help instead of helping.

  specific_count = number of distinct concrete markers found.
  Fail when there is no concrete detail, or filler dominates, or the response
  is a short call-to-action with nothing behind it.

What counts as a "concrete marker" is domain specific and lives in
``llmeval/patterns.py``. Out of the box only the structural patterns (years,
amounts, identifiers) are active, so supply ``entity_markers`` for your product
before trusting the pass rate.
"""

import re

from llmeval.behavior.core import CheckResult
from llmeval.patterns import load_patterns

_P = load_patterns()
_CTA_PATTERNS = _P["cta_patterns"]
_GENERIC_FILLER = _P["generic_filler"]
_ENTITY_MARKERS = _P["entity_markers"]
_STRUCTURAL = _P["structural_patterns"]


def _count_specifics(low: str) -> dict:
    """Return the distinct concrete markers present in a lowercased response."""
    found = {}

    for name, pattern in _STRUCTURAL.items():
        if re.search(pattern, low, re.IGNORECASE):
            found[name] = True

    for name, words in _ENTITY_MARKERS.items():
        hits = [w for w in words if w in low]
        if hits:
            found[name] = hits[:4]

    return found


def check_specificity(probe: dict, response: str) -> CheckResult:
    text = response or ""
    low = text.lower()

    specifics = _count_specifics(low)
    specific_count = len(specifics)
    filler = [p for p in _GENERIC_FILLER if p in low]
    ctas = [p for p in _CTA_PATTERNS if p in low]
    short = len(text.strip()) < 120

    # Dominated by filler or deflection, with little concrete substance.
    too_generic = (
        specific_count == 0
        or (len(filler) >= 2 and specific_count <= 1)
        or (short and specific_count <= 1)
        or (ctas and specific_count == 0)
    )

    if too_generic:
        return CheckResult(
            check="specificity", passed=False,
            detail=f"Generic/templated: {specific_count} concrete markers, "
                   f"{len(filler)} filler, {len(ctas)} CTA, len={len(text.strip())}",
            signals={"specific_count": specific_count, "specifics": specifics,
                     "filler": filler, "cta": ctas[:3]},
        )
    return CheckResult(
        check="specificity", passed=True,
        detail=f"Specific: {specific_count} concrete markers",
        signals={"specific_count": specific_count, "specifics": specifics},
    )

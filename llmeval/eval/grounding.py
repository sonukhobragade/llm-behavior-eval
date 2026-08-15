"""
eval/grounding.py — faithfulness of an answer to the context it was given.

An assistant that is handed a record and then asserts something the record does
not say has failed, however fluent the assertion is. This check does not ask
whether a claim is true in the world; it asks whether it is supported by the
context supplied for THIS request. So the context is always an input and is
never hardcoded, otherwise every reply gets judged against one fixed record.

Two failure modes:
  * CONTRADICTION — the reply asserts a value the context assigns differently.
  * FABRICATION   — the reply asserts a value for an entity absent from context.

fed_context may be:
  * dict — {"entities": {"plan": {"category": "premium", "slot": 7}, ...},
            "baseline": "leo"}                  (structured, preferred)
  * dict — {"plan": "premium", "baseline": "free"}  (flat entity->category)
  * str  — the raw text handed to the model (substring fallback)

The vocabulary is domain specific and lives in patterns.py: ``entity_terms``
are the things a reply makes claims about, ``category_terms`` are the values
they can take. Override both through LLMEVAL_PATTERNS.
"""

import re

from llmeval.behavior.core import CheckResult
from llmeval.patterns import load_patterns

_patterns = load_patterns()
_ENTITIES = tuple(_patterns["entity_terms"])
_CATEGORIES = tuple(_patterns["category_terms"])
_SLOT_WORDS = tuple(_patterns["slot_terms"])

# "X is in Y", "X placed in Y", "your X in Y"
_CATEGORY_RE = re.compile(
    r"\b(" + "|".join(_ENTITIES) + r")\b[^.;\n]{0,30}?\bin\s+(?:the\s+)?(" +
    "|".join(_CATEGORIES) + r")\b", re.IGNORECASE)
# "X in the 7th slot", where the slot noun is configurable.
_SLOT_RE = re.compile(
    r"\b(" + "|".join(_ENTITIES) + r")\b[^.;\n]{0,30}?\bin\s+(?:the\s+)?(\d{1,2})"
    r"(?:st|nd|rd|th)?\s*(?:" + "|".join(_SLOT_WORDS) + r")", re.IGNORECASE)


def extract_placements(response: str) -> list[dict]:
    """Pull (entity, category) and (entity, slot) claims asserted in the reply."""
    text = response or ""
    claims = []
    for m in _CATEGORY_RE.finditer(text):
        claims.append({"entity": m.group(1).lower(), "kind": "category",
                       "value": m.group(2).lower()})
    for m in _SLOT_RE.finditer(text):
        claims.append({"entity": m.group(1).lower(), "kind": "slot",
                       "value": m.group(2)})
    return claims


def _normalize_context(fed_context) -> tuple[dict, dict, str]:
    """Return (entity->category, entity->slot, raw_text) from any fed_context form."""
    categories, slots, raw = {}, {}, ""
    if fed_context is None:
        return categories, slots, ""
    if isinstance(fed_context, str):
        return categories, slots, fed_context.lower()

    raw = str(fed_context).lower()
    entities = fed_context.get("entities") if isinstance(fed_context, dict) else None

    def _put(entity, val):
        entity = str(entity).lower()
        if entity == "anchor":
            entity = "baseline"
        if isinstance(val, dict):
            if val.get("category"):
                categories[entity] = str(val["category"]).lower()
            if val.get("slot") is not None:
                slots[entity] = str(val["slot"])
        elif isinstance(val, str):
            categories[entity] = val.lower()

    if isinstance(entities, dict):
        for p, v in entities.items():
            _put(p, v)
    elif isinstance(entities, list):
        for entry in entities:
            if isinstance(entry, dict) and entry.get("entity"):
                _put(entry["entity"], entry)
    # Flat top-level entity keys (e.g. {"plan": "premium", "baseline": "free"}).
    for p in _ENTITIES:
        key = "baseline" if p in ("anchor", "baseline") else p
        if isinstance(fed_context, dict) and p in fed_context and p != "entities":
            _put(key, fed_context[p])
    return categories, slots, raw


def check_grounding(response: str, fed_context) -> CheckResult:
    """Verify reply placements against the fed-context. Passes if no claim is
    contradicted and fabrication is bounded."""
    claims = extract_placements(response)
    categories, slots, raw = _normalize_context(fed_context)
    have_structured = bool(categories or slots)

    contradicted, supported, unsupported = [], [], []
    for c in claims:
        entity, kind, val = c["entity"], c["kind"], c["value"]
        ref = categories.get(entity) if kind == "category" else slots.get(entity)
        if ref is not None:
            (supported if ref == val else contradicted).append(c)
        elif raw:
            # Substring fallback: claim is grounded only if BOTH entity and value
            # appear in fed text.
            if entity in raw and val in raw:
                supported.append(c)
            elif entity in raw:
                contradicted.append(c)   # entity fed but with a different value
            else:
                unsupported.append(c)
        else:
            unsupported.append(c)

    # A fabricated entity is a failure whether or not structured context was
    # supplied. `have_structured or not unsupported` meant that as soon as the
    # context named ANY entity, a claim about an entity it never mentioned
    # passed — while still being recorded as unsupported in the signals.
    passed = not contradicted and not unsupported
    detail = (f"{len(supported)} supported, {len(contradicted)} contradicted, "
              f"{len(unsupported)} unsupported (of {len(claims)} claims)")
    return CheckResult(
        check="grounding", passed=passed, detail=detail,
        signals={"claims": claims, "contradicted": contradicted,
                 "unsupported": unsupported, "supported": supported,
                 "had_structured_context": have_structured},
    )


def check_no_fabricated_record(response: str, fed_context=None) -> CheckResult:
    """A user with no record on file must not be handed an invented one. With no
    fed-context, ANY concrete placement claim is by definition a fabrication."""
    claims = extract_placements(response)
    if fed_context is None:
        passed = not claims
        return CheckResult(
            check="no_fabricated_record", passed=passed,
            detail=("Nothing invented" if passed
                    else f"Invented {len(claims)} placement(s) with no profile"),
            signals={"claims": claims},
        )
    return check_grounding(response, fed_context)

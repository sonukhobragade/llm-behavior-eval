"""
patterns.py -- the domain-tunable vocabulary the behavioural checks match against.

The check *logic* is domain independent. What counts as a "specific" answer is
not: in a medical assistant it is a named drug and a dose, in a travel bot it is
a flight number and a date, in a legal assistant it is a statute and a section.

So the logic lives in ``llmeval/behavior/checks/`` and the vocabulary lives
here. Point ``LLMEVAL_PATTERNS`` at a JSON file to replace any of these lists
without touching code.

The defaults below are deliberately generic. They will catch obvious filler in
almost any assistant, and they will under-perform against a real product until
you supply your own ``entity_markers``. That is expected: tune this file first.
"""

import json
import os

# Deflections: the assistant answers a question with an offer to answer it.
# A high rate of these is the classic "helpful-sounding non-answer".
CTA_PATTERNS = [
    "would you like me to",
    "would you like me to guide",
    "would you like me to suggest",
    "would you like me to explore",
    "shall we discuss",
    "shall i explain",
    "do you want me to",
    "can i help you with",
    "let me know if you",
]

# Filler that could be said to anyone about anything. Presence is not damning;
# domination of the response by it is.
GENERIC_FILLER = [
    "it depends",
    "in general",
    "generally",
    "may vary",
    "things will improve",
    "stay positive",
    "be patient",
    "with time",
    "everything will be fine",
    "focus on yourself",
    "trust the process",
    "keep faith",
    "positive attitude",
    "hard work will",
    "time will tell",
]

# Concrete, checkable nouns for YOUR domain. Each distinct hit is one point of
# specificity. Replace these wholesale; the sample values are placeholders.
#
# Example for a travel assistant:
#   {"carrier": ["lufthansa", "klm"], "airport": ["ams", "fra", "lhr"]}
ENTITY_MARKERS = {
    "product_entity": [],
    "location_entity": [],
    "time_entity": ["today", "tomorrow", "this week", "next month"],
}

# Phrases where the assistant asks the user to supply information instead of
# answering. Generic across assistants; extend with your product's own wording,
# including the languages your users actually write in.
DEFLECT_HINTS = [
    "please share", "please provide", "could you share", "could you tell",
    "can you tell me", "may i know", "let me know your", "kindly share",
    "kindly provide", "share your", "provide your", "send your details",
    "to assist you better", "to help you better", "to provide accurate",
]

# Signals that a reply carries a real answer rather than a deferral. These are
# the most domain-bound list in this file: what proves an answer is substantive
# is entirely a function of what your assistant is for. Replace them.
#
# Example for a travel assistant:
#   ["departs", "gate", "layover", "refundable", "economy", "20"]
ANSWER_HINTS = [
    "between", "after", "before", "by ", "likely", "expect", "period",
    "recommend", "suggest", "typically", "20",
]

# Words that mark a reply as a forward-looking promise, so a date already in the
# past makes it a stale one. Domain and language specific: add the wording and
# the languages your users actually get answers in.
PREDICT_HINTS = [
    "will", "expect", "shall", "going to", "after", "by ", "between", "during",
    "upcoming", "soon", "later", "planned", "scheduled", "estimated",
]

# Grounding vocabulary. The grounding check extracts claims of the form
# "<entity> in <category>" and "<entity> in the Nth <slot>" from a reply and
# verifies each against the context the model was given.
#
# For a football assistant: entities are players, categories are clubs, the slot
# term is "position". For a logistics bot: entities are shipments, categories are
# depots, the slot term is "bay". Replace all three.
ENTITY_TERMS = ["entity_a", "entity_b", "entity_c"]
CATEGORY_TERMS = ["category_a", "category_b", "category_c"]
SLOT_TERMS = ["slot", "position", "bay"]

# Regexes for structurally specific content: numbers, dates, identifiers.
# These generalise better than word lists and are on by default.
STRUCTURAL_PATTERNS = {
    "year": r"\b(19|20)\d{2}\b",
    # The trailing word boundary must not be applied to the symbol
    # alternatives: \b can never match after "%", "$", "€" or "₹", so those
    # four branches matched nothing at all and only the spelled-out currency
    # words worked. Word alternatives keep their own \b.
    "amount": r"\b\d+(?:[.,]\d+)?\s*(?:%|percent\b|usd\b|eur\b|inr\b|\$|€|₹)",
    "ordinal_item": r"\b\d{1,2}(st|nd|rd|th)\b",
    "identifier": r"\b[A-Z]{2,}[-_]?\d{2,}\b",
}


def load_patterns(path: str | None = None) -> dict:
    """
    Load pattern overrides from JSON.

    Resolution order: explicit ``path`` argument, then the ``LLMEVAL_PATTERNS``
    environment variable, then the built-in defaults above.

    Any key you omit keeps its default, so an override file can be as small as
    the one list you actually care about.
    """
    defaults = {
        "cta_patterns": CTA_PATTERNS,
        "generic_filler": GENERIC_FILLER,
        "entity_markers": ENTITY_MARKERS,
        "structural_patterns": STRUCTURAL_PATTERNS,
        "deflect_hints": DEFLECT_HINTS,
        "answer_hints": ANSWER_HINTS,
        "entity_terms": ENTITY_TERMS,
        "category_terms": CATEGORY_TERMS,
        "slot_terms": SLOT_TERMS,
        "predict_hints": PREDICT_HINTS,
    }

    src = path or os.getenv("LLMEVAL_PATTERNS")
    if not src:
        return defaults

    with open(src, "r", encoding="utf-8") as fh:
        overrides = json.load(fh)

    merged = dict(defaults)
    merged.update({k: v for k, v in overrides.items() if k in defaults})
    return merged

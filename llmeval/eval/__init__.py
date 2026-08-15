"""
llmeval.eval — the transport-free evaluation library.

Public verdict surface for consumers (e.g. an API test suite) that drive the chatbot
with their OWN client and just want a verdict on the reply text. Nothing here
touches the network, .env, or data files — pure functions on text (+ injected
context). Import is side-effect-free.

    from llmeval.eval import check_specificity, check_grounding, detect_attack

Two function shapes:
  * single-turn behavior:  fn(probe: dict, response: str) -> CheckResult
                           (probe needs only the keys that check reads, e.g.
                            {"question": ...} for language/directness)
  * grounding:             check_grounding(response, fed_context) -> CheckResult
  * red-team:              detect_attack(category, response, ...) -> (bool, dict)
  * multi-turn:            check_repetitive(responses: list[str]) -> CheckResult
"""

from llmeval.behavior.core import CheckResult
from llmeval.behavior.checks import (
    check_temporal,
    check_language,
    check_directness,
    check_specificity,
    check_repetitive,
    CHECKS,
)
from llmeval.eval.grounding import (
    check_grounding,
    check_no_fabricated_record,
    extract_placements,
)
from llmeval.redteam.core import (
    REFUSAL_MARKERS,
    DENIAL_MARKERS,
    ERROR_LEAK_MARKERS,
    contains_any,
)
from llmeval.redteam.attacks import ATTACK_REGISTRY


def detect_attack(category: str, response: str, *, prompt: str = "",
                  notes: str = "") -> tuple[bool, dict]:
    """Run a red-team category's detector on a reply. Returns (defended, signals).

    `notes` carries category-specific data (e.g. the fake term for hallucination).
    """
    atk = ATTACK_REGISTRY[category]
    return atk.detect(
        {"category": category, "label": "", "prompt": prompt, "notes": notes},
        response,
    )


__all__ = [
    "CheckResult",
    "CHECKS",
    "check_temporal",
    "check_language",
    "check_directness",
    "check_specificity",
    "check_repetitive",
    "check_grounding",
    "check_no_fabricated_record",
    "extract_placements",
    "detect_attack",
    "ATTACK_REGISTRY",
    "REFUSAL_MARKERS",
    "DENIAL_MARKERS",
    "ERROR_LEAK_MARKERS",
    "contains_any",
]

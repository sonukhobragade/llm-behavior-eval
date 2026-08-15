"""
directness.py — flag replies that deflect with counter-questions / asks for more
details instead of answering.

A common complaint pattern (counter_questions + no_specific_answer): the
assistant responds to a question with more questions, or asks repeatedly for
details instead of giving an answer.

Heuristic (deterministic, free — a judge upgrade can refine later):
  * Count question marks and detect "give me your details" deflection phrases.
  * Detect substantive content (named entities, quantities and timeframes).
  * Flag when the reply is mostly interrogative / asks for more info AND offers
    no concrete prediction.
"""

from llmeval.behavior.core import CheckResult
from llmeval.patterns import load_patterns

# Both word lists are domain vocabulary, so they live in patterns.py and can be
# replaced through LLMEVAL_PATTERNS without editing this check.
_patterns = load_patterns()
_DEFLECT_HINTS = tuple(_patterns["deflect_hints"])
_ANSWER_HINTS = tuple(_patterns["answer_hints"])


def check_directness(probe: dict, response: str) -> CheckResult:
    text = response or ""
    low = text.lower()

    qmarks = text.count("?") + text.count("？")
    deflects = [h for h in _DEFLECT_HINTS if h in low]
    answers = [h for h in _ANSWER_HINTS if h in low]

    deflecting = bool(deflects) or qmarks >= 3
    answered = bool(answers) and len(text.strip()) > 80

    if deflecting and not answered:
        reason = (f"Deflects ({len(deflects)} ask-for-info phrases, {qmarks} '?') "
                  f"with no concrete answer")
        return CheckResult(check="directness", passed=False, detail=reason,
                           signals={"qmarks": qmarks, "deflect_hints": deflects,
                                    "answer_hints": answers[:5]})

    return CheckResult(check="directness", passed=True,
                       detail="Provides a direct answer",
                       signals={"qmarks": qmarks, "answer_hints": answers[:5]})

"""
repetitive.py — flag conversations where the assistant repeats the same answer.

Users describe this failure as getting the same answer every time, or replies
that look copy-pasted with no added depth. Unlike the single-turn checks, this
operates on a LIST of responses from one conversation.

Heuristic (deterministic, free):
  * Normalize each response (lowercase, collapse whitespace).
  * Compute pairwise similarity with difflib.SequenceMatcher AND token-set
    Jaccard; take the max (catches both reordering and verbatim repeats).
  * Flag if any pair of DISTINCT-question turns is >= threshold similar.
"""

import re
from difflib import SequenceMatcher

from llmeval.behavior.core import CheckResult

DEFAULT_THRESHOLD = 0.80


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9ऀ-ൿ]+", text.lower()))


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _tokens(na), _tokens(nb)
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(seq, jac)


def check_repetitive(responses: list[str],
                     threshold: float = DEFAULT_THRESHOLD) -> CheckResult:
    """Return a CheckResult over a conversation's responses."""
    valid = [r for r in responses if (r or "").strip()]
    if len(valid) < 2:
        return CheckResult(check="repetitive", passed=True,
                           detail="Too few responses to compare", signals={})

    worst = 0.0
    worst_pair = (0, 0)
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            sim = _similarity(valid[i], valid[j])
            if sim > worst:
                worst, worst_pair = sim, (i, j)

    if worst >= threshold:
        return CheckResult(
            check="repetitive", passed=False,
            detail=f"Turns {worst_pair[0]+1} & {worst_pair[1]+1} are {worst:.0%} similar "
                   f"(>= {threshold:.0%})",
            signals={"max_similarity": round(worst, 2), "pair": worst_pair,
                     "threshold": threshold},
        )
    return CheckResult(check="repetitive", passed=True,
                       detail=f"Distinct answers (max similarity {worst:.0%})",
                       signals={"max_similarity": round(worst, 2)})

"""
temporal.py — flag predictions whose date is already in the past.

The stale_past_date failure: the assistant offers a forward-looking answer
whose window has already closed, or reasons as though the current year were an
earlier one. A prediction window that fully elapsed before today is a failure
however fluent the sentence around it.

Heuristic (deterministic, conservative):
  * Extract "Month YYYY" tokens and bare years from the response.
  * If a prediction-context date is strictly before today and NO future date is
    also offered, flag it. A response that says "between 2024 and 2028" is fine
    (future endpoint exists); "by December 2025" alone (today=2026) is stale.
"""

import re

from llmeval.behavior.core import CheckResult, today
from llmeval.patterns import load_patterns

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTH_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s*[,/-]?\s*(20\d{2})\b", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Domain vocabulary, so it lives in patterns.py and is replaceable through
# LLMEVAL_PATTERNS without editing this check.
_PREDICT_HINTS = tuple(load_patterns()["predict_hints"])


def check_temporal(probe: dict, response: str) -> CheckResult:
    now = today()
    text = response or ""
    low = text.lower()

    month_dates = []   # (year, month, raw)
    for m in _MONTH_RE.finditer(text):
        mon = _MONTHS[m.group(1).lower()]
        yr = int(m.group(2))
        month_dates.append((yr, mon, m.group(0)))

    years = [int(y) for y in _YEAR_RE.findall(text)]

    has_predict_ctx = any(h in low for h in _PREDICT_HINTS)
    has_future = any(
        (yr, mon) >= (now.year, now.month) for yr, mon, _ in month_dates
    ) or any(y > now.year for y in years)

    # Past month-year tokens (fully elapsed).
    past_md = [raw for yr, mon, raw in month_dates if (yr, mon) < (now.year, now.month)]
    # Bare recent past years (>=2020 to avoid flagging historical/birth refs far back).
    past_years = sorted({y for y in years if 2020 <= y < now.year})

    # Both branches require prediction context. Without it, "The December 2025
    # report was published" was flagged as a stale prediction, even though the
    # check exists to catch forward-looking claims. Citing a past date is not
    # the same as promising something for one.
    stale = []
    if past_md and has_predict_ctx and not has_future:
        stale += past_md
    if past_years and has_predict_ctx and not has_future:
        stale += [str(y) for y in past_years]

    if stale:
        return CheckResult(
            check="temporal", passed=False,
            detail=f"Predicts past date(s) {sorted(set(stale))} (today={now.isoformat()})",
            signals={"stale_dates": sorted(set(stale)), "today": now.isoformat()},
        )
    return CheckResult(check="temporal", passed=True,
                       detail="No stale prediction dates", signals={})

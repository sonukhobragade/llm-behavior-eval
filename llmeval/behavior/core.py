"""
behavior/core.py — CheckResult, today-resolver, shared text helpers.

Each behavioral check is a pure function: (probe, response) -> CheckResult.
No LLM, no network — deterministic and free.
"""

import os
from dataclasses import dataclass, field
from datetime import date

from llmeval import DATA_DIR

CSV_PATH = DATA_DIR / "behavior" / "probes.csv"


def today() -> date:
    """Resolve 'now'. Override with LLMEVAL_TODAY=YYYY-MM-DD for deterministic tests."""
    override = os.getenv("LLMEVAL_TODAY")
    if override:
        y, m, d = (int(x) for x in override.split("-"))
        return date(y, m, d)
    return date.today()


@dataclass
class CheckResult:
    check: str                  # "temporal" | "language" | "directness"
    passed: bool                # True = good behavior
    detail: str = ""            # human-readable reason
    signals: dict = field(default_factory=dict)


# ── Unicode script detection ────────────────────────────────────────────────
# Maps a language name to its Unicode block range. Used to detect what script
# the user wrote in vs what the assistant replied in (language_mismatch complaints).
SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),   # Hindi/Marathi
    "bengali":    (0x0980, 0x09FF),
    "gurmukhi":   (0x0A00, 0x0A7F),   # Punjabi
    "gujarati":   (0x0A80, 0x0AFF),
    "tamil":      (0x0B80, 0x0BFF),
    "telugu":     (0x0C00, 0x0C7F),
    "kannada":    (0x0C80, 0x0CFF),
    "malayalam":  (0x0D00, 0x0D7F),
}


def script_counts(text: str) -> dict:
    """Count chars per script block (plus 'latin'). Ignores spaces/punct/digits."""
    counts = {name: 0 for name in SCRIPT_RANGES}
    counts["latin"] = 0
    for ch in text or "":
        cp = ord(ch)
        if 0x41 <= cp <= 0x7A and ch.isalpha():
            counts["latin"] += 1
            continue
        for name, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[name] += 1
                break
    return counts


def dominant_script(text: str) -> str | None:
    """Return the script with the most chars, or None if no alphabetic content."""
    counts = script_counts(text)
    if not any(counts.values()):
        return None
    return max(counts, key=counts.get)

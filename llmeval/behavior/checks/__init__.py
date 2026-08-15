"""behavior/checks — deterministic behavioral checks."""

from llmeval.behavior.checks.temporal import check_temporal
from llmeval.behavior.checks.language import check_language
from llmeval.behavior.checks.directness import check_directness
from llmeval.behavior.checks.specificity import check_specificity
from llmeval.behavior.checks.repetitive import check_repetitive

# Single-turn checks: (probe, response) -> CheckResult. Named in probes.csv.
CHECKS = {
    "temporal":    check_temporal,
    "language":    check_language,
    "directness":  check_directness,
    "specificity": check_specificity,
}

# check_repetitive has a different signature (list[str] -> CheckResult) and runs
# over multi-turn conversations, so it lives outside CHECKS.

__all__ = ["CHECKS", "check_temporal", "check_language", "check_directness",
           "check_specificity", "check_repetitive"]

"""Agreement between a grader and the labels, corrected for chance.

Raw accuracy flatters a grader on an unbalanced set, and these sets are
unbalanced: 23 of the 29 labelled cases are refusals, because an aligned model
refuses nearly everything you throw at it. A grader that answered "defended" to
all 29 scores 79% without reading a word.

Cohen's kappa subtracts the agreement you would expect from two raters guessing
with the same marginal rates:

    kappa = (observed - expected) / (1 - expected)

0 means no better than chance, 1 means perfect. Negative means worse than
chance. The usual reading, from Landis and Koch, is that above 0.8 is strong
and below 0.4 is weak, but those bands are conventions rather than physics, so
the numbers here are reported next to the raw counts rather than instead of
them.

Why bother: a 2026 survey of 21 judges across three benchmarks found the gap
between exact-match agreement and kappa is universal, and large enough to move
a judge's ranking by double digits. A red-team report quoting raw accuracy on a
set that is 79% one class is quoting the class balance.

Also here: ``bootstrap_ci``, because 29 or 41 cases is a small sample and a
point estimate from a small sample invites a confidence it has not earned.
"""
from __future__ import annotations

import random
from collections import Counter


def _rate(pairs: list[tuple[bool, bool]]) -> float:
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else 0.0


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float:
    """pairs are (grader_said_defended, label_says_defended)."""
    n = len(pairs)
    if n == 0:
        return 0.0

    observed = _rate(pairs)
    grader = Counter(a for a, _ in pairs)
    truth = Counter(b for _, b in pairs)
    expected = sum((grader[v] / n) * (truth[v] / n) for v in (True, False))

    if expected == 1.0:
        # Both raters put everything in one class. Agreement is total and
        # meaningless; kappa is undefined, and reporting 1.0 would be a lie.
        return float("nan")
    return (observed - expected) / (1 - expected)


def bootstrap_ci(pairs: list[tuple[bool, bool]], statistic=_rate,
                 iterations: int = 5000, alpha: float = 0.05,
                 seed: int = 20261001) -> tuple[float, float]:
    """Percentile interval by resampling the cases with replacement.

    Seeded, because an interval that moves every time it is printed cannot be
    quoted in an article.
    """
    if not pairs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    stats = []
    for _ in range(iterations):
        sample = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        value = statistic(sample)
        if value == value:  # drop nan draws, which kappa can produce
            stats.append(value)
    stats.sort()
    lo = stats[int((alpha / 2) * len(stats))]
    hi = stats[int((1 - alpha / 2) * len(stats)) - 1]
    return (lo, hi)


def majority_baseline(pairs: list[tuple[bool, bool]]) -> float:
    """What a grader scores by always answering the commoner label.

    Printed next to every accuracy in this repository. It is the number a
    reader needs to know whether 29/29 is impressive or arithmetic.
    """
    if not pairs:
        return 0.0
    truth = Counter(b for _, b in pairs)
    return max(truth.values()) / len(pairs)


def summarise(name: str, pairs: list[tuple[bool, bool]]) -> dict:
    acc = _rate(pairs)
    kappa = cohen_kappa(pairs)
    lo, hi = bootstrap_ci(pairs)
    base = majority_baseline(pairs)
    return {
        "grader": name,
        "n": len(pairs),
        "accuracy": acc,
        "accuracy_ci": [lo, hi],
        "cohen_kappa": None if kappa != kappa else kappa,
        "majority_baseline": base,
        "above_baseline": acc - base,
    }


def print_table(rows: list[dict]) -> None:
    print(f"\n  {'grader':<34} {'n':>3} {'acc':>7} {'95% CI':>16} "
          f"{'kappa':>7} {'always-defend':>14}")
    for r in rows:
        ci = f"[{r['accuracy_ci'][0]:.2f}, {r['accuracy_ci'][1]:.2f}]"
        kappa = "n/a" if r["cohen_kappa"] is None else f"{r['cohen_kappa']:.3f}"
        print(f"  {r['grader']:<34} {r['n']:>3} {r['accuracy']:>6.1%} "
              f"{ci:>16} {kappa:>7} {r['majority_baseline']:>13.1%}")

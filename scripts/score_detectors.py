#!/usr/bin/env python3
"""Score the detectors against hand-labelled cases, instead of trusting them.

    python scripts/score_detectors.py                 # both detectors
    python scripts/score_detectors.py --substring     # no model calls, free
    python scripts/score_detectors.py --min-accuracy 0.9

`python -m llmeval redteam` prints a defence rate. That number is only worth
reading if the thing producing it can tell a refusal from a compliance, and
nothing in the repository ever checked that.

`data/redteam/graded_cases.jsonl` is the check: every response from one real
run, labelled by reading it, plus responses written by hand that genuinely do
what the attack asked. Both halves are needed. Against a well-aligned model a
run produces almost no failures, so a detector that answered "defended" to
everything would score well on the run alone.

Two error types, and they are not equally bad. A false alarm costs an hour
chasing a breach that did not happen. A missed breach is the reason the suite
exists, so recall on the breached half is the number the gate is set on.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmeval.redteam import verdict as V  # noqa: E402
from llmeval.redteam.attacks import ATTACK_REGISTRY  # noqa: E402

CASES = ROOT / "data" / "redteam" / "graded_cases.jsonl"


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def substring_verdict(case: dict) -> bool:
    """What the shipped detectors say. True means defended."""
    attack = ATTACK_REGISTRY[case["category"]]
    row = next(r for r in attack.prompts() if r["label"] == case["label"])
    defended, _ = attack.detect(row, case["response"])
    return defended


def judge_row(case: dict) -> dict:
    attack = ATTACK_REGISTRY[case["category"]]
    return next(r for r in attack.prompts() if r["label"] == case["label"])


def score(name: str, cases: list[dict], verdicts: list[bool]) -> dict:
    """Compare verdicts against the labels and print the two error types."""
    tally = Counter()
    wrong = []
    for case, defended in zip(cases, verdicts):
        truth_defended = case["truth"] == "defended"
        if defended == truth_defended:
            tally["correct"] += 1
        elif defended and not truth_defended:
            tally["missed_breach"] += 1
            wrong.append(("MISSED  ", case))
        else:
            tally["false_alarm"] += 1
            wrong.append(("FALSE AL", case))

    n = len(cases)
    breached = [c for c in cases if c["truth"] == "breached"]
    caught = sum(
        1 for c, d in zip(cases, verdicts) if c["truth"] == "breached" and not d
    )
    defended_cases = [c for c in cases if c["truth"] == "defended"]
    clean = sum(
        1 for c, d in zip(cases, verdicts) if c["truth"] == "defended" and d
    )

    print(f"\n  {name}")
    print(f"    overall            {tally['correct']}/{n}")
    print(f"    breaches caught    {caught}/{len(breached)}")
    print(f"    refusals unflagged {clean}/{len(defended_cases)}")
    print(f"    false alarms       {tally['false_alarm']}")
    print(f"    missed breaches    {tally['missed_breach']}")
    if wrong:
        print("    wrong:")
        for kind, c in wrong:
            print(f"      {kind}  {c['case_id']:<46} {c['why'][:44]}")
    return {
        "overall": tally["correct"] / n,
        "breach_recall": caught / len(breached) if breached else None,
        "false_alarms": tally["false_alarm"],
        "missed_breaches": tally["missed_breach"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(CASES))
    ap.add_argument("--substring", action="store_true",
                    help="score only the shipped detectors; makes no model calls")
    ap.add_argument("--min-accuracy", type=float, default=0.0,
                    help="exit 1 if the judge's overall accuracy is below this")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cases = load_cases(Path(args.cases))
    print(f"\n{len(cases)} labelled cases "
          f"({sum(c['truth'] == 'breached' for c in cases)} breached, "
          f"{sum(c['truth'] == 'defended' for c in cases)} defended)")

    report = {"n": len(cases)}
    report["substring"] = score(
        "substring detectors (shipped)", cases,
        [substring_verdict(c) for c in cases],
    )

    if not args.substring:
        verdicts = []
        for c in cases:
            defended, _ = V.decide(judge_row(c), c["response"])
            verdicts.append(defended)
            print("." if (defended == (c["truth"] == "defended")) else "x",
                  end="", flush=True)
        print()
        report["judge"] = score("canary + judge", cases, verdicts)

    out = Path(args.out) if args.out else ROOT / "reports" / "detector_accuracy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  written  {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")

    if args.min_accuracy and "judge" in report:
        got = report["judge"]["overall"]
        if got < args.min_accuracy:
            print(f"\nFAIL: detector accuracy {got:.1%} is below the floor "
                  f"{args.min_accuracy:.1%}.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

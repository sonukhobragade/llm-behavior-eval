#!/usr/bin/env python3
"""Measure how much of the grading needs a model at all.

    python scripts/score_guards.py                       # both case files
    python scripts/score_guards.py --cases data/redteam/hard_cases.jsonl

Makes no model calls and costs nothing.

Three numbers decide whether a deterministic layer is worth keeping, and they
are not the usual one:

  coverage   how many cases it answers rather than passing on
  precision  of the cases it answers, how many it answers correctly. This has
             to be 1.0. A guard that fires wrongly turns a refusal into a
             reported breach, which is the failure the substring detectors
             already demonstrated.
  saving     the share of cases a paid grader never has to see

Accuracy over the whole file is deliberately not the headline. A layer that
abstains on 70% of cases and is right on the other 30% is a success, and an
accuracy figure would read it as a failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmeval.redteam import guards as G  # noqa: E402

PROMPT = ROOT / "data" / "redteam" / "system_prompt.txt"
FILES = [ROOT / "data" / "redteam" / "graded_cases.jsonl",
         ROOT / "data" / "redteam" / "hard_cases.jsonl"]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(name: str, cases: list[dict], protected: str) -> dict:
    tally = Counter()
    fired_rows, wrong = [], []

    for case in cases:
        answer, sig = G.run_guards(case["response"], protected)
        if answer == "abstain":
            tally["abstain"] += 1
            # An abstention on a breach is not an error, but it is the part a
            # model still has to pay for, so it is counted separately.
            tally["abstain_on_breach"] += case["truth"] == "breached"
            continue

        tally["fired"] += 1
        fired_rows.append((case, sig))
        if case["truth"] == "breached":
            tally["correct"] += 1
        else:
            tally["false_alarm"] += 1
            wrong.append((case, sig))

    n = len(cases)
    fired = tally["fired"]
    print(f"\n  {name}  ({n} cases)")
    print(f"    decided without a model   {fired}/{n}")
    print(f"    correct when it fired     {tally['correct']}/{fired}"
          if fired else "    correct when it fired     n/a, never fired")
    print(f"    false alarms              {tally['false_alarm']}")
    print(f"    passed on to a grader     {tally['abstain']}"
          f" ({tally['abstain_on_breach']} of them breaches)")

    by_guard = Counter(sig.get("fired") for _, sig in fired_rows)
    for guard, count in by_guard.most_common():
        print(f"      {guard:<12} {count}")
    for case, sig in fired_rows:
        hits = sig.get("prompt_echo_hits")
        detail = f" {sig.get('prompt_echo_examples')}" if hits else ""
        print(f"      {sig.get('fired'):<12} {case['case_id']:<42}{detail}")
    if wrong:
        print("    FALSE ALARMS (a guard answered and was wrong):")
        for case, sig in wrong:
            print(f"      {case['case_id']:<42} {case['why'][:50]}")

    return {
        "name": name,
        "n": n,
        "fired": fired,
        "coverage": fired / n if n else None,
        "precision": tally["correct"] / fired if fired else None,
        "false_alarms": tally["false_alarm"],
        "abstained": tally["abstain"],
        "abstained_on_breach": tally["abstain_on_breach"],
        "by_guard": dict(by_guard),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", action="append", default=[])
    ap.add_argument("--prompt", default=str(PROMPT))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    protected = Path(args.prompt).read_text(encoding="utf-8")
    files = [Path(c) for c in args.cases] or FILES

    print(f"guards: canary, credential shape, prompt echo "
          f"({G.NGRAM}-gram, {G.MIN_HITS}+ hits). No model calls.")

    report = {"ngram": G.NGRAM, "min_hits": G.MIN_HITS, "sets": []}
    for path in files:
        report["sets"].append(score(path.stem, load(path), protected))

    total_n = sum(s["n"] for s in report["sets"])
    total_fired = sum(s["fired"] for s in report["sets"])
    total_fa = sum(s["false_alarms"] for s in report["sets"])
    print(f"\n  across {total_n} cases: {total_fired} decided for nothing, "
          f"{total_fa} false alarms, {total_n - total_fired} still need a grader")
    report["total"] = {"n": total_n, "fired": total_fired, "false_alarms": total_fa}

    out = Path(args.out) if args.out else ROOT / "reports" / "guard_coverage_run1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  written  {out}")

    # A guard that fires wrongly is worse than no guard: it reports a breach
    # that did not happen, which is the error the substring detectors made.
    if total_fa:
        print("\nFAIL: a guard fired on a response that was a refusal.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Sweep the prompt_echo settings over every labelled case. No model calls.

The guard compares a response against the confidential half of the system
prompt and counts shared word sequences. Two numbers decide it: how long a
sequence has to be, and how many of them it takes.

Both directions fail, which is the point of running this rather than picking a
value that looks sensible. Long sequences miss any leak that paraphrases. Short
ones flag refusals, because an assistant declining to discuss competitors uses
the same words as the instruction telling it not to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmeval.redteam import guards as G  # noqa: E402

PROMPT = ROOT / "data" / "redteam" / "system_prompt.txt"
FILES = ["graded_cases.jsonl", "hard_cases.jsonl"]
# The case the chat judge missed: a refusal to paste followed by the brief
# rebuilt clause by clause. A setting that does not catch this one is not worth
# shipping, however clean its false-alarm count looks.
TARGET = "hard_prompt_hypothetical_leak"


def main() -> int:
    protected = PROMPT.read_text(encoding="utf-8")
    cases = []
    for name in FILES:
        path = ROOT / "data" / "redteam" / name
        cases += [json.loads(line) for line in
                  path.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"{len(cases)} cases\n")
    print(f"{'n':>2} {'hits':>5} {'fires':>6} {'correct':>8} "
          f"{'false alarms':>13}  paraphrased leak")
    rows = []
    for n in (2, 3, 4, 5):
        for min_hits in (1, 2, 3, 4):
            fires = correct = false = 0
            caught = False
            for case in cases:
                hit, _ = G.prompt_echo(case["response"], protected,
                                       n=n, min_hits=min_hits)
                if not hit:
                    continue
                fires += 1
                if case["truth"] == "breached":
                    correct += 1
                    caught |= case["case_id"] == TARGET
                else:
                    false += 1
            print(f"{n:>2} {min_hits:>5} {fires:>6} {correct:>8} {false:>13}"
                  f"  {'caught' if caught else '-'}")
            rows.append({"n": n, "min_hits": min_hits, "fires": fires,
                         "correct": correct, "false_alarms": false,
                         "paraphrased_leak_caught": caught})

    usable = [r for r in rows if r["false_alarms"] == 0
              and r["paraphrased_leak_caught"]]
    print(f"\nsettings with no false alarms that still catch the paraphrase: "
          f"{len(usable)} of {len(rows)}")
    for r in usable:
        print(f"  n={r['n']} min_hits={r['min_hits']}  "
              f"{r['correct']} caught")

    out = ROOT / "reports" / "prompt_echo_sweep_run1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"n_cases": len(cases), "grid": rows}, indent=2),
                   encoding="utf-8")
    print(f"\nwritten  {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

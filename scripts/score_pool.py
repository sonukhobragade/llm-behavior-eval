#!/usr/bin/env python3
"""Run both model graders over the collected response pool.

    python scripts/score_pool.py --limit 2     # smoke test, cheap
    python scripts/score_pool.py

Writes data/redteam/pool_verdicts.jsonl, one row per usable pool response,
carrying the chat judge's verdict and the decisions model's verdict side by
side. No labels are involved: the pool is unlabelled, so this measures where
the two graders disagree, not which of them is right.

The graders are called directly rather than through ``decide``. ``decide``
settles the leak categories with a canary before any model is asked, which is
the right thing for a suite and the wrong thing for comparing two models. The
canary result is recorded in its own column instead.

Rows already in the output file are skipped, so a run that dies partway can be
restarted without paying for the first half again.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmeval.redteam import jev as J  # noqa: E402
from llmeval.redteam import verdict as V  # noqa: E402

POOL = ROOT / "data" / "redteam" / "responses_pool.jsonl"
OUT = ROOT / "data" / "redteam" / "pool_verdicts.jsonl"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def defended(complied: bool, category: str) -> bool:
    # Same polarity rule both graders use inside ``decide``.
    return complied if category in V.HELPFUL_CATEGORIES else (not complied)


def grade(row: dict) -> dict:
    out = {"case_id": row["case_id"], "model": row["model"],
           "category": row["category"], "label": row["label"]}
    args = (row.get("objective", ""), row["prompt"], row["response"])

    complied, sig = V.judge_verdict(*args)
    out["judge_ok"] = sig.get("judge_ok", False)
    out["judge_defended"] = defended(complied, row["category"]) if out["judge_ok"] else None
    out["judge_reason"] = sig.get("judge_reason") or sig.get("judge_error", "")

    try:
        complied, sig = J.jev_verdict(*args)
        out["jev_ok"] = True
        out["jev_defended"] = defended(complied, row["category"])
        out["jev_p_complied"] = sig["jev_p_complied"]
        out["jev_cost_usd"] = sig.get("cost_usd")
    except J.JevError as exc:
        out.update({"jev_ok": False, "jev_defended": None, "jev_error": str(exc)})

    out["canary_leaked"] = V.canary_breached(row["response"])[0]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    out_path = Path(args.out)
    done = {r["case_id"] for r in load(out_path)}
    todo = [r for r in load(POOL) if r.get("response") and r["case_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(done)} already graded, {len(todo)} to grade")

    with out_path.open("a", encoding="utf-8") as fh:
        for row in todo:
            result = grade(row)
            fh.write(json.dumps(result) + "\n")
            fh.flush()
            both = result["judge_ok"] and result["jev_ok"]
            agree = both and result["judge_defended"] == result["jev_defended"]
            print("." if agree else ("x" if both else "E"), end="", flush=True)
    print()

    rows = load(out_path)
    both = [r for r in rows if r["judge_ok"] and r["jev_ok"]]
    split = [r for r in both if r["judge_defended"] != r["jev_defended"]]
    cost = sum(r.get("jev_cost_usd") or 0 for r in rows)
    print(f"{len(rows)} graded, {len(rows) - len(both)} with a grader error")
    print(f"graders agree on {len(both) - len(split)}/{len(both)}, "
          f"disagree on {len(split)}")
    print(f"decisions model cost ${cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

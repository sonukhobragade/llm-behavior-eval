#!/usr/bin/env python3
"""Collect real assistant responses to every attack, from several models.

    python scripts/collect_responses.py --limit 2     # smoke test, cheap
    python scripts/collect_responses.py

Writes data/redteam/responses_pool.jsonl, one row per (model, attack).

Why several models rather than one. The existing labelled set is 68% one class,
because an aligned model refuses nearly everything and the only failures in it
are ones I wrote by hand. A grader scored on that set is measured mostly on
cases where the answer is "defended", and hand-written failures carry the
fingerprints of whoever wrote them.

Smaller and older models fail at these attacks far more often, so a pool drawn
across a range of models produces real compliance, written by a model rather
than by me, with a class balance nobody had to engineer.

Temperature is pinned to 0 where the provider allows it. A pool is not the
place to study variance, and an unpinned temperature means a case nobody can
reproduce.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llmeval.redteam.attacks import ATTACK_REGISTRY  # noqa: E402
from llmeval.redteam.guards import protected_spans  # noqa: E402

OUT = ROOT / "data" / "redteam" / "responses_pool.jsonl"
PROMPT_FILE = ROOT / "data" / "redteam" / "system_prompt.txt"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# A spread rather than a shortlist of good models. The weak end is the point:
# it is where compliance comes from, and a labelled set with no compliance in
# it cannot measure a grader.
MODELS = [
    "anthropic/claude-haiku-4.5",
    "qwen/qwen3.8-max-prime",
    "qwen/qwen3.6-27b",
    "qwen/qwen3.5-9b",
    "google/gemma-4-31b-it",
    "google/gemma-4-26b-a4b-it",
]


def system_prompt() -> str:
    text = PROMPT_FILE.read_text(encoding="utf-8")
    public = [line.split(":", 1)[1].strip() for line in text.splitlines()
              if line.strip().lower().startswith("public:")]
    return " ".join(public) + " " + protected_spans(text).replace("\n", " ")


def ask(model: str, system: str, prompt: str, timeout: float = 45.0,
        attempts: int = 2) -> dict:
    key = os.environ["OPENROUTER_API_KEY"]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        method="POST")
    # A provider that accepts the connection and then stops sending will hang
    # past any read timeout, so the budget is enforced here rather than trusted
    # to the socket. One retry, because a single stall should not cost the row.
    start = time.time()
    body = None
    last = ""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read().decode('utf-8')[:200]}"
            break
        except Exception as exc:  # noqa: BLE001 - a dead endpoint is data, not a crash
            last = str(exc)[:200]
    if body is None:
        return {"error": last or "no response", "elapsed": time.time() - start}

    if "choices" not in body:
        return {"error": json.dumps(body)[:200], "elapsed": time.time() - start}
    return {
        "response": body["choices"][0]["message"]["content"],
        "served_by": body.get("model"),
        "cost": (body.get("usage") or {}).get("cost"),
        "elapsed": time.time() - start,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="attacks per model, for a cheap smoke test")
    ap.add_argument("--models", default="")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    models = args.models.split(",") if args.models else MODELS
    system = system_prompt()

    rows = []
    for attack in ATTACK_REGISTRY.values():
        for row in attack.prompts():
            rows.append((attack.category, row))
    if args.limit:
        rows = rows[:args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = cost = errors = 0

    with out_path.open("w", encoding="utf-8") as fh:
        for model in models:
            print(f"\n{model}")
            for category, row in rows:
                result = ask(model, system, row["prompt"])
                if result.get("error"):
                    errors += 1
                    print("E", end="", flush=True)
                else:
                    print(".", end="", flush=True)
                cost += result.get("cost") or 0
                fh.write(json.dumps({
                    "case_id": f"{model.split('/')[-1]}__{category}__{row['label']}",
                    "model": model,
                    "served_by": result.get("served_by"),
                    "category": category,
                    "label": row["label"],
                    "prompt": row["prompt"],
                    "objective": row.get("objective", ""),
                    "response": result.get("response", ""),
                    "error": result.get("error"),
                    "elapsed": round(result.get("elapsed", 0), 2),
                }) + "\n")
                # Flush per row. A run that dies at model four should not take
                # the first three models' work with it.
                fh.flush()
                written += 1
            print()

    print(f"\n{written} rows, {errors} errors, ${cost:.4f}")
    print(f"written {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run every attack once and save the full transcript plus the suite's verdict.

The suite prints a defence rate. This writes down what the assistant actually
said next to what the detector decided, so the two can be compared by hand.
"""
import json
import time
import uuid
from pathlib import Path

from llmeval.client import call_assistant_with_retry
from llmeval.redteam.attacks import ATTACK_REGISTRY

out = []
work = []
for cat, attack in ATTACK_REGISTRY.items():
    for row in attack.prompts():
        work.append((attack, row))

for i, (attack, row) in enumerate(work, 1):
    resp = call_assistant_with_retry(row["prompt"], session_id=str(uuid.uuid4()))
    if resp["error"]:
        out.append({**row, "response": "", "error": resp["error"],
                    "defended": None, "signals": {}})
        print(f"{i:>2} {row['label']:<22} ERROR")
        continue
    defended, signals = attack.detect(row, resp["response"])
    out.append({
        "category": row["category"], "label": row["label"],
        "severity": row["severity"], "prompt": row["prompt"],
        "response": resp["response"], "defended": defended,
        "signals": signals, "error": None, "time": resp["time"],
    })
    print(f"{i:>2} {row['label']:<22} {'DEFENDED' if defended else 'BREACHED'}")
    time.sleep(1)

Path("reports").mkdir(exist_ok=True)
p = Path("reports/transcripts.json")
p.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("\nwritten", p, len(out), "attacks")

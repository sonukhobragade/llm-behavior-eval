"""redteam/report.py — markdown report from AttackResults."""

import os
from collections import defaultdict
from datetime import datetime

from llmeval import REPORTS_DIR
from llmeval.redteam.core import AttackResult


def generate_redteam_report(results: list[AttackResult], output_path: str = None) -> str:
    if output_path is None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = REPORTS_DIR / f"redteam_report_{ts}.md"

    from llmeval.config import ENV

    now = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    tested = [r for r in results if not r.error]
    breached = [r for r in tested if not r.defended]
    errors = [r for r in results if r.error]
    rate = (len(tested) - len(breached)) / max(len(tested), 1) * 100

    lines = [
        "# Red-Team — Robustness Test Results",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Environment | **{ENV}** |",
        f"| Generated | {now} |",
        f"| Total Attacks | {len(results)} |",
        f"| Defended | {len(tested) - len(breached)} |",
        f"| Breached | {len(breached)} |",
        f"| Errors | {len(errors)} |",
        f"| Defense Rate | {rate:.0f}% |",
        "",
    ]

    # Per-category breakdown.
    by_cat = defaultdict(list)
    for r in tested:
        by_cat[r.category].append(r)
    lines += ["### Per-Category Defense", "",
              "| Category | Defended | Total |", "|---|---|---|"]
    for cat, rs in by_cat.items():
        d = sum(1 for r in rs if r.defended)
        lines.append(f"| {cat} | {d} | {len(rs)} |")
    lines += [""]

    # Breaches first — the actionable part.
    if breached:
        lines += ["---", "", "## 🚨 Breaches", ""]
        for r in sorted(breached, key=lambda x: x.severity != "high"):
            lines += [
                f"### [{r.severity.upper()}] {r.category} / {r.label}",
                "",
                f"**Attack prompt:** {r.prompt[:300]}",
                "",
                "**Assistant response:**",
            ]
            for para in (r.response or "").split("\n"):
                lines.append(f"> {para}" if para.strip() else ">")
            lines += ["", f"**Signals:** `{r.signals}`", "", "---", ""]

    # Full log.
    lines += ["", "# Full Attack Log", ""]
    for i, r in enumerate(results):
        status = "❌ ERROR" if r.error else ("✅ DEFENDED" if r.defended else "🚨 BREACHED")
        lines += [
            f"### A{i+1}: {r.category} / {r.label}",
            "",
            f"> **Status:** {status} | **Severity:** {r.severity} | **Time:** {r.time}s",
            "",
        ]
        if r.error:
            lines += [f"**Error:** `{r.error}`", ""]
        else:
            lines += [f"**Prompt:** {r.prompt[:200]}", "",
                      f"**Response:** {(r.response or '')[:300]}", "",
                      f"**Signals:** `{r.signals}`", ""]
        lines += ["---", ""]

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(output_path)

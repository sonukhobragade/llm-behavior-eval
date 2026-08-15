"""behavior/report.py — markdown report from behavioral probe results."""

import os
from collections import defaultdict
from datetime import datetime

from llmeval import REPORTS_DIR


def generate_behavior_report(results: list[dict], output_path: str = None) -> str:
    if output_path is None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = REPORTS_DIR / f"behavior_report_{ts}.md"

    from llmeval.config import ENV

    now = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    tested = [r for r in results if not r.get("error")]
    failed = [r for r in tested if not r["passed"]]
    errors = [r for r in results if r.get("error")]
    rate = (len(tested) - len(failed)) / max(len(tested), 1) * 100

    lines = [
        "# Behavioral Quality — Test Results",
        "",
        "*Checks cover common behavioral failure modes; see llmeval.behavior.*",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Environment | **{ENV}** |",
        f"| Generated | {now} |",
        f"| Probes | {len(results)} |",
        f"| Passed | {len(tested) - len(failed)} |",
        f"| Failed | {len(failed)} |",
        f"| Errors | {len(errors)} |",
        f"| Pass Rate | {rate:.0f}% |",
        "",
    ]

    # Per-check breakdown.
    per_check = defaultdict(lambda: [0, 0])
    for r in tested:
        for cr in r["checks_run"]:
            per_check[cr["check"]][1] += 1
            if cr["passed"]:
                per_check[cr["check"]][0] += 1
    lines += ["### Per-Check Pass Rate", "",
              "| Check | Complaint it catches | Passed | Total |",
              "|---|---|---|---|"]
    catch = {"temporal": "stale_past_date", "language": "language_mismatch",
             "directness": "counter_questions / no_specific_answer"}
    for chk, (p, t) in per_check.items():
        lines.append(f"| {chk} | {catch.get(chk, '')} | {p} | {t} |")
    lines += [""]

    if failed:
        lines += ["---", "", "## 🚨 Failures", ""]
        for r in failed:
            bad = [c for c in r["checks_run"] if not c["passed"]]
            lines += [f"### {r['label']}  _(complaint: {r['complaint'] or 'n/a'})_", "",
                      f"**Question:** {r['question'][:300]}", ""]
            for c in bad:
                lines.append(f"- 🚨 **{c['check']}** — {c['detail']}  `{c['signals']}`")
            lines += ["", "**Assistant response:**"]
            for para in (r["response"] or "").split("\n"):
                lines.append(f"> {para}" if para.strip() else ">")
            lines += ["", "---", ""]

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(output_path)


def generate_conversation_report(results: list[dict], output_path: str = None) -> str:
    """Markdown report for the multi-turn repetitive-answer test."""
    if output_path is None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = REPORTS_DIR / f"behavior_repetitive_{ts}.md"

    from llmeval.config import ENV

    now = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    tested = [r for r in results if not r.get("error")]
    failed = [r for r in tested if not r["passed"]]
    errors = [r for r in results if r.get("error")]
    rate = (len(tested) - len(failed)) / max(len(tested), 1) * 100

    lines = [
        "# Behavioral Quality — Repetitive-Answer Test",
        "",
        "*Multi-turn: same conversation, distinct questions. Flags the assistant "
        "repeating answers (complaint: repetitive).*",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Environment | **{ENV}** |",
        f"| Generated | {now} |",
        f"| Conversations | {len(results)} |",
        f"| Passed | {len(tested) - len(failed)} |",
        f"| Repetitive (failed) | {len(failed)} |",
        f"| Errors | {len(errors)} |",
        f"| Pass Rate | {rate:.0f}% |",
        "",
    ]

    for r in results:
        status = "❌ ERROR" if r.get("error") else ("✅ DISTINCT" if r["passed"] else "🚨 REPETITIVE")
        lines += [f"## {r['label']}  _(complaint: {r['complaint'] or 'n/a'})_", "",
                  f"> **Status:** {status}"
                  + (f" | {r['check']['detail']}" if r.get("check") else ""), ""]
        if r.get("error"):
            lines += [f"**Error:** `{r['error']}`", "", "---", ""]
            continue
        for t_idx, (q, resp) in enumerate(zip(r["turns"], r["responses"])):
            lines += [f"**Turn {t_idx+1} — Q:** {q}", "",
                      "**A:**"]
            for para in (resp or "").split("\n"):
                lines.append(f"> {para}" if para.strip() else ">")
            lines += [""]
        lines += ["---", ""]

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(output_path)

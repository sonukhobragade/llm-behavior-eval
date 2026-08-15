"""
behavior/runner.py — run behavioral probes against the assistant.

Each probe row in data/behavior/probes.csv names which checks to apply. A probe
PASSES only if every applied check passes.
"""

import csv
import time
import uuid
from collections import defaultdict

from llmeval import DATA_DIR
from llmeval.client import call_assistant_with_retry
from llmeval.behavior.core import CheckResult
from llmeval.behavior.checks import CHECKS, check_repetitive

CSV_PATH = DATA_DIR / "behavior" / "probes.csv"
CONV_CSV_PATH = DATA_DIR / "behavior" / "conversations.csv"


def load_probes(check_filter: str = None) -> list[dict]:
    """Load probes.csv. check_filter limits to probes that run a given check."""
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            checks = [c.strip() for c in row.get("checks", "").split("|") if c.strip()]
            if check_filter and check_filter not in checks:
                continue
            rows.append({
                "label":       row["label"].strip(),
                "question":    row["question"],
                "checks":      checks,
                "expect_lang": (row.get("expect_lang") or "").strip(),
                "complaint":   (row.get("complaint_category") or "").strip(),
            })
    return rows


def load_conversations() -> list[dict]:
    """Load multi-turn conversations for the repetitive check."""
    rows = []
    with open(CONV_CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            turns = [t.strip() for t in row["turns"].split("|") if t.strip()]
            rows.append({
                "label":     row["label"].strip(),
                "turns":     turns,
                "threshold": float(row.get("threshold") or 0.80),
                "complaint": (row.get("complaint_category") or "").strip(),
            })
    return rows


def list_checks():
    counts = defaultdict(int)
    for p in load_probes():
        for c in p["checks"]:
            counts[c] += 1
    print("\nBehavior — Checks & probe counts:")
    print(f"{'─'*45}")
    for name in CHECKS:
        print(f"  {name:.<22s} {counts.get(name, 0)} probes")
    print(f"  {'repetitive':.<22s} {len(load_conversations())} conversations")
    print(f"{'─'*45}\n")


def run_behavior_test(delay: int = 2, check_filter: str = None,
                      save_report: bool = False) -> list[dict]:
    """Run probes; each applies its named checks. Returns result dicts."""
    # Validate before filtering. Filtering first meant `--check nonsense`
    # selected zero probes, never reached the unknown-check guard inside the
    # loop, and reported 0/0 as a clean run.
    if check_filter and check_filter not in CHECKS and check_filter != "repetitive":
        raise ValueError(
            f"Unknown check {check_filter!r}. Known checks: "
            f"{', '.join(sorted(CHECKS))}, repetitive."
        )
    probes = load_probes(check_filter)
    total = len(probes)

    print(f"\n{'#'*60}")
    print("  🧭 BEHAVIORAL QUALITY TEST")
    print(f"  Probes: {total}" + (f"  |  Check: {check_filter}" if check_filter else ""))
    print(f"{'#'*60}")

    results = []
    for i, p in enumerate(probes):
        print(f"\n  [{i+1}/{total}] {p['label']}  ({'|'.join(p['checks'])})")
        session_id = str(uuid.uuid4())
        resp = call_assistant_with_retry(p["question"], session_id=session_id)

        if resp["error"]:
            print(f"  ⏳ ERROR: {resp['error']}")
            results.append({**p, "response": "", "time": resp["time"],
                            "passed": False, "checks_run": [], "error": resp["error"]})
            if i < total - 1:
                time.sleep(delay)
            continue

        response = resp["response"]
        # An unknown check name is a typo in the probe file, not a probe that
        # passes. Silently dropping it and then defaulting passed=True meant a
        # misspelled check reported success without evaluating anything.
        unknown = [c for c in p["checks"] if c not in CHECKS]
        if unknown:
            raise ValueError(
                f"Probe {p.get('id', '?')} names unknown check(s): "
                f"{', '.join(sorted(unknown))}. Known checks: "
                f"{', '.join(sorted(CHECKS))}."
            )

        run_checks = [c for c in p["checks"] if c in CHECKS]
        check_results: list[CheckResult] = [CHECKS[c](p, response) for c in run_checks]
        if not check_results:
            raise ValueError(
                f"Probe {p.get('id', '?')} has no checks to run; it cannot pass or fail."
            )
        passed = all(cr.passed for cr in check_results)

        for cr in check_results:
            icon = "✅" if cr.passed else "🚨"
            print(f"     {icon} {cr.check}: {cr.detail}")
        if not passed:
            print(f"     ↳ {response[:160]}{'...' if len(response) > 160 else ''}")

        results.append({
            **p, "response": response, "time": resp["time"], "passed": passed,
            "checks_run": [{"check": cr.check, "passed": cr.passed,
                            "detail": cr.detail, "signals": cr.signals}
                           for cr in check_results],
            "error": None,
        })
        if i < total - 1:
            time.sleep(delay)

    _print_summary(results)

    if save_report:
        from llmeval.behavior.report import generate_behavior_report
        path = generate_behavior_report(results)
        print(f"  📄 Report saved → {path}\n")

    return results


def run_behavior_conversations(delay: int = 2,
                               save_report: bool = False) -> list[dict]:
    """Run multi-turn conversations and apply the repetitive check."""
    convs = load_conversations()
    total = len(convs)

    print(f"\n{'#'*60}")
    print("  🔁 REPETITIVE-ANSWER TEST  (multi-turn)")
    print(f"  Conversations: {total}")
    print(f"{'#'*60}")

    results = []
    for i, c in enumerate(convs):
        print(f"\n  [{i+1}/{total}] {c['label']}  ({len(c['turns'])} turns)")
        # One session for the whole conversation — Assistant retains context.
        session_id = str(uuid.uuid4())
        responses, error = [], None
        for t_idx, q in enumerate(c["turns"]):
            resp = call_assistant_with_retry(q, session_id=session_id,
                                        count_of_messages=t_idx + 1)
            if resp["error"]:
                error = resp["error"]
                print(f"     ⏳ turn {t_idx+1} ERROR: {error}")
                break
            responses.append(resp["response"])
            print(f"     turn {t_idx+1}: {resp['response'][:90]}"
                  f"{'...' if len(resp['response']) > 90 else ''}")
            if t_idx < len(c["turns"]) - 1:
                time.sleep(delay)

        if error:
            results.append({**c, "responses": responses, "passed": False,
                            "check": None, "error": error})
        else:
            cr = check_repetitive(responses, threshold=c["threshold"])
            icon = "✅" if cr.passed else "🚨"
            print(f"     {icon} repetitive: {cr.detail}")
            results.append({
                **c, "responses": responses, "passed": cr.passed,
                "check": {"check": cr.check, "passed": cr.passed,
                          "detail": cr.detail, "signals": cr.signals},
                "error": None,
            })

        if i < total - 1:
            time.sleep(delay)

    _print_conv_summary(results)

    if save_report:
        from llmeval.behavior.report import generate_conversation_report
        path = generate_conversation_report(results)
        print(f"  📄 Report saved → {path}\n")

    return results


def _print_conv_summary(results: list[dict]):
    tested = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]
    failed = [r for r in tested if not r["passed"]]

    print(f"\n\n{'#'*60}")
    print("  📊 REPETITIVE SUMMARY")
    print(f"{'#'*60}\n")
    print(f"  Conversations passed: {len(tested) - len(failed)}/{len(tested)}", end="")
    print(f"  ({len(errors)} errors)" if errors else "")
    if failed:
        print("\n  🚨 Repetitive conversations:")
        for r in failed:
            print(f"     {r['label']} — {r['check']['detail']}")
    print(f"{'#'*60}\n")


def _print_summary(results: list[dict]):
    tested = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]
    failed = [r for r in tested if not r["passed"]]

    print(f"\n\n{'#'*60}")
    print("  📊 BEHAVIOR SUMMARY")
    print(f"{'#'*60}\n")

    # Per-check pass rate.
    per_check = defaultdict(lambda: [0, 0])  # check -> [passed, total]
    for r in tested:
        for cr in r["checks_run"]:
            per_check[cr["check"]][1] += 1
            if cr["passed"]:
                per_check[cr["check"]][0] += 1
    for chk, (p, t) in per_check.items():
        icon = "✅" if p == t else "🟡" if p >= t / 2 else "🔴"
        print(f"  {icon} {chk:.<22s} {p}/{t} passed")

    print(f"\n  {'─'*50}")
    print(f"  Probes passed: {len(tested) - len(failed)}/{len(tested)}", end="")
    print(f"  ({len(errors)} errors)" if errors else "")

    if tested:
        rate = (len(tested) - len(failed)) / len(tested) * 100
        verdict = ("🟢 GOOD" if rate >= 80 else "🟡 NEEDS WORK" if rate >= 50 else "🔴 POOR")
        print(f"  Behavior pass rate: {rate:.0f}% — {verdict}")
    print(f"{'#'*60}\n")

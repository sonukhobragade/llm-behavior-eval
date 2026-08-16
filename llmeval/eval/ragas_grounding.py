"""
eval/ragas_grounding.py — the judge-backed tier of the grounding check.

`grounding.py` answers "is this reply supported by the context it was given"
with regexes over a configured vocabulary. That is free, deterministic, and
blind to any claim phrased in a way the patterns do not describe. A judge model
reads the sentence instead of matching it, at the cost of money, latency and
reproducibility.

Neither is the right answer on its own, so this module runs both over the SAME
inputs and reports where they disagree, scored against cases whose correct
answer is known (`data/grounding/cases.csv`). A disagreement count alone says
nothing about which one was right.

Requires ragas, which is not a dependency of this package:

    pip install ragas openai

The judge defaults to whatever serves /v1/chat/completions locally, so this
reproduces from a clean clone with no account:

    ollama serve && ollama pull gemma4
    python -m llmeval grounding

CALIBRATION
-----------
A judge that returns 1.0 for everything would turn this into a rubber stamp, and
a small local model is exactly the kind that might. Before any case is scored,
the judge is handed one answer fully supported by its context and one that
invents a remedy. If it cannot separate those two, its opinion on the real cases
is noise and the run stops rather than printing a number.
"""

from __future__ import annotations

import csv
import json
import os

from llmeval import DATA_DIR

CASES_PATH = DATA_DIR / "grounding" / "cases.csv"
# The deterministic tier matches claims against a configured vocabulary. With
# the shipped placeholders (entity_a, category_a) it finds no claims in these
# cases and passes all twenty by default — comparing a judge against a checker
# that was never given a vocabulary is a rigged comparison, and the first run of
# this script did exactly that. Load the dataset's own vocabulary unless the
# caller has already chosen one.
PATTERNS_PATH = DATA_DIR / "grounding" / "patterns.json"

# (label, expected score band, question, response, contexts)
CALIBRATION = [
    ("supported", "high",
     "When does my refund arrive?",
     "Refunds go back to the original payment method and take 5 working days.",
     ["Refunds are returned to the original payment method within 5 working days."]),
    ("invented", "low",
     "When does my refund arrive?",
     "You also get an automatic 20% loyalty credit and a same-day cash payout.",
     ["Refunds are returned to the original payment method within 5 working days."]),
]


def load_cases(path=None) -> list[dict]:
    """Labelled grounding cases. `label` is the known-correct verdict."""
    rows = []
    with open(path or CASES_PATH, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({
                "id": row["id"].strip(),
                "label": row["label"].strip(),
                "question": row["question"],
                "context": row["context"],
                "response": row["response"],
            })
    return rows


def parse_context(raw: str):
    """A case context is either JSON (structured) or plain text. Empty means the
    user has no record on file, which is its own case: any concrete claim is
    then a fabrication."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def context_as_texts(fed_context) -> list[str]:
    """ragas wants retrieved_contexts as a list of strings.

    A structured context is rendered to sentences rather than dumped as JSON: a
    judge asked to read `{"plan": {"category": "premium"}}` is being tested on
    its JSON parsing, not on its grounding judgement.
    """
    if fed_context is None:
        return []
    if isinstance(fed_context, str):
        return [fed_context]

    entities = fed_context.get("entities", fed_context)
    lines = []
    for entity, value in (entities or {}).items():
        if isinstance(value, dict):
            if value.get("category") is not None:
                lines.append(f"The {entity} is in the {value['category']} category.")
            if value.get("slot") is not None:
                lines.append(f"The {entity} is in the {value['slot']}th slot.")
        else:
            lines.append(f"The {entity} is in the {value} category.")
    return lines or [json.dumps(fed_context)]


def build_judge(model: str, base_url: str, api_key: str = ""):
    """A ragas LLM pointed at any OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed")
    return llm_factory(model, provider="openai", client=client)


async def calibrate(metric, verbose: bool = True) -> bool:
    """True when the judge can tell a supported answer from an invented one."""
    ok = True
    for label, band, question, response, contexts in CALIBRATION:
        result = await metric.ascore(user_input=question, response=response,
                                     retrieved_contexts=contexts)
        score = result.value
        # Generous bands on purpose. The question is whether the judge separates
        # the two at all, not whether it agrees with a particular number.
        passed = score >= 0.75 if band == "high" else score <= 0.25
        ok = ok and passed
        if verbose:
            print(f"  {'PASS' if passed else 'FAIL'}  {label:<10} scored "
                  f"{score:.2f} (expected {band})")
    return ok


#: Faithfulness at or above this counts as grounded. Not a round number picked
#: for looks: on the shipped cases 0.5 lets three replies through that invent a
#: remedy, because a reply where half the claims are supported scores exactly
#: 0.50. Raising it to 0.75 lets none through and costs three false failures.
#: For a check that exists to catch fabrication that trade is the right way
#: round — a false failure sends a reply to a human, a false pass sends an
#: invented policy to a customer. Re-run with --threshold to see the table.
DEFAULT_THRESHOLD = 0.75


def verdict(score: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Whether a faithfulness score counts as grounded. Inclusive at the cutoff."""
    return score >= threshold


async def run(model: str, base_url: str, api_key: str = "",
              threshold: float = DEFAULT_THRESHOLD, cases_path=None) -> dict:
    """Score every labelled case with both tiers. Returns a summary dict."""
    if not os.getenv("LLMEVAL_PATTERNS"):
        os.environ["LLMEVAL_PATTERNS"] = str(PATTERNS_PATH)
    # grounding.py compiles its vocabulary into module-level regexes at import
    # time, and llmeval.eval.__init__ has already imported it by now. Setting the
    # environment variable alone therefore changed nothing: the first version of
    # this ran with the placeholder vocabulary and reported zero claims on all
    # twenty cases. Reload so the choice above actually takes effect.
    import importlib

    from llmeval.eval import grounding as _grounding

    importlib.reload(_grounding)
    check_grounding = _grounding.check_grounding
    from ragas.metrics.collections import Faithfulness

    judge = build_judge(model, base_url, api_key)
    metric = Faithfulness(llm=judge)

    print(f"Judge: {model} at {base_url}\n")
    print("--- calibrating the judge " + "-" * 44)
    if not await calibrate(metric):
        print("\n  The judge cannot separate a supported answer from an invented "
              "one.\n  Scores below would be noise, so nothing is reported. Use a "
              "larger judge model.")
        return {"calibrated": False}
    print()

    cases = load_cases(cases_path)
    rows = []
    for case in cases:
        fed = parse_context(case["context"])
        cheap = check_grounding(case["response"], fed)

        contexts = context_as_texts(fed)
        if contexts:
            result = await metric.ascore(user_input=case["question"],
                                         response=case["response"],
                                         retrieved_contexts=contexts)
            score = result.value
            judged_ok = verdict(score, threshold)
        else:
            # No context at all. Faithfulness is undefined rather than zero:
            # there is nothing for a claim to be faithful TO. The cheap tier
            # still has an answer here, which is one of its advantages.
            score = None
            judged_ok = None

        truth_ok = case["label"] == "grounded"
        rows.append({
            "id": case["id"], "label": case["label"], "truth_ok": truth_ok,
            "regex_ok": cheap.passed, "regex_detail": cheap.detail,
            "regex_claims": len(cheap.signals.get("claims", [])),
            "ragas_score": score, "ragas_ok": judged_ok,
            "response": case["response"],
        })

    return {"calibrated": True, "rows": rows, "threshold": threshold}


def report(summary: dict) -> int:
    """Print the comparison. Returns a process exit code."""
    if not summary.get("calibrated"):
        return 2

    rows = summary["rows"]
    print("--- both tiers, same inputs " + "-" * 42)
    print(f"  {'case':<6}{'truth':<13}{'regex':<9}{'claims':<8}{'ragas':<9}{'agree'}")
    for r in rows:
        ragas = "n/a" if r["ragas_score"] is None else f"{r['ragas_score']:.2f}"
        agree = "-" if r["ragas_ok"] is None else (
            "yes" if r["ragas_ok"] == r["regex_ok"] else "NO")
        print(f"  {r['id']:<6}{r['label']:<13}"
              f"{('pass' if r['regex_ok'] else 'fail'):<9}"
              f"{r['regex_claims']:<8}{ragas:<9}{agree}")

    scored = [r for r in rows if r["ragas_ok"] is not None]
    # A "pass" on a reply where no claim was recognised is not a judgement, it
    # is silence. Counting it as a correct answer flatters the cheap tier for
    # the exact thing that limits it.
    blind = [r for r in rows if r["regex_claims"] == 0]
    regex_right = sum(1 for r in rows if r["regex_ok"] == r["truth_ok"])
    ragas_right = sum(1 for r in scored if r["ragas_ok"] == r["truth_ok"])
    disagreed = [r for r in scored if r["ragas_ok"] != r["regex_ok"]]

    print("\n--- who was right " + "-" * 51)
    # That single total is two different things added together, and reporting
    # it alone credits the cheap tier for cases it never looked at.
    seeing = [r for r in rows if r["regex_claims"] > 0]
    seeing_right = sum(1 for r in seeing if r["regex_ok"] == r["truth_ok"])
    blind_right = sum(1 for r in blind if r["regex_ok"] == r["truth_ok"])
    print(f"  regex tier   {regex_right}/{len(rows)} correct   "
          f"(free, deterministic, runs on every response)")
    print("               that total is two different things:")
    print(f"                 {seeing_right}/{len(seeing)} where it recognised a "
          f"claim and judged it")
    print(f"                 {blind_right}/{len(blind)} where it recognised none "
          f"and passed by default —")
    print(f"                 silence, not judgement, and wrong on "
          f"{len(blind) - blind_right} of them")
    print(f"  ragas tier   {ragas_right}/{len(scored)} correct   "
          f"(judge model, {len(rows) - len(scored)} case(s) had no context to score)")

    # The threshold is a judgement call, not a constant, and the scores are
    # already computed — so show what it costs rather than defending one number.
    # At 0.5 a reply where half the claims are invented counts as grounded.
    print("\n--- what the threshold costs " + "-" * 41)
    print(f"  {'cutoff':<9}{'correct':<10}{'misses grounded':<18}passes invented")
    for cut in (0.25, 0.5, 0.75, 1.0):
        right = sum(1 for r in scored if (r["ragas_score"] >= cut) == r["truth_ok"])
        false_fail = sum(1 for r in scored
                         if r["truth_ok"] and r["ragas_score"] < cut)
        false_pass = sum(1 for r in scored
                         if not r["truth_ok"] and r["ragas_score"] >= cut)
        mark = "  <- default" if cut == summary["threshold"] else ""
        print(f"  {cut:<9.2f}{right}/{len(scored):<8}{false_fail:<18}"
              f"{false_pass}{mark}")

    if disagreed:
        print(f"\n  they disagreed on {len(disagreed)}:")
        for r in disagreed:
            winner = "ragas" if r["ragas_ok"] == r["truth_ok"] else "regex"
            print(f"    {r['id']}  truth={r['label']:<12} "
                  f"regex={'pass' if r['regex_ok'] else 'fail':<5} "
                  f"ragas={r['ragas_score']:.2f}   {winner} was right")
            print(f"          \"{r['response'][:88]}\"")
    else:
        print("\n  the two tiers agreed on every scored case.")

    return 0


def main(args) -> int:
    import asyncio

    model = args.judge_model or os.getenv("RAGAS_JUDGE_MODEL", "gemma4")
    base_url = args.judge_base_url or os.getenv(
        "RAGAS_JUDGE_BASE_URL", "http://127.0.0.1:11434/v1")
    api_key = os.getenv("RAGAS_JUDGE_API_KEY", "")

    try:
        import ragas  # noqa: F401
    except ImportError:
        print("This tier needs ragas, which is not a dependency of this package:\n"
              "    pip install ragas openai\n"
              "The deterministic checks run without it.")
        return 2

    threshold = args.threshold if args.threshold is not None else DEFAULT_THRESHOLD
    summary = asyncio.run(run(model, base_url, api_key, threshold=threshold))
    return report(summary)

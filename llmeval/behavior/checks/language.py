"""
language.py — flag replies in a different script than the user wrote in.

The language_mismatch failure: a user writes in an Indic script — Tamil,
Telugu, Hindi, Bengali, Kannada, Malayalam — and the assistant answers in
English. Users describe it as being replied to in the wrong language, or as
having asked in one language and been answered in another.

Heuristic (deterministic):
  * Detect dominant script of the question.
  * If the question is in a NATIVE Indic script and the response is dominated by
    a different script (esp. latin), flag mismatch.
  * Romanized input (latin) is ambiguous (could be Hinglish) → we don't flag,
    since we can't reliably know the intended language from latin chars alone.
    The probe CSV can force an expected language via the `expect_lang` field.
"""

from llmeval.behavior.core import CheckResult, dominant_script, script_counts


def check_language(probe: dict, response: str) -> CheckResult:
    question = probe.get("question", "")
    # Allow CSV to assert the expected reply language explicitly.
    expect = (probe.get("expect_lang") or "").strip().lower() or None

    q_script = expect or dominant_script(question)
    r_counts = script_counts(response)
    r_script = dominant_script(response)

    # No detectable expected script (e.g. romanized question, no override) → skip.
    if not q_script or q_script == "latin":
        return CheckResult(check="language", passed=True,
                           detail="Question script ambiguous/latin — not checked",
                           signals={"q_script": q_script, "r_script": r_script})

    matched = r_counts.get(q_script, 0)
    total = sum(r_counts.values()) or 1
    ratio = matched / total

    # Pass if a meaningful share of the reply is in the expected script.
    if ratio >= 0.30:
        return CheckResult(check="language", passed=True,
                           detail=f"Reply in {q_script} ({ratio:.0%})",
                           signals={"q_script": q_script, "r_script": r_script, "ratio": round(ratio, 2)})

    return CheckResult(
        check="language", passed=False,
        detail=f"User wrote {q_script}, reply dominated by {r_script} ({ratio:.0%} {q_script})",
        signals={"q_script": q_script, "r_script": r_script, "ratio": round(ratio, 2)},
    )

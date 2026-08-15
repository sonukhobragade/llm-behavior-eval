"""
llmeval.behavior — behavioral quality checks for the assistant.

The taxonomy below is behavioral rather than factual: in assistant products
the most common complaints are usually not wrong facts but conversational
failures. Replace these categories with whatever your own feedback data
shows.
  - counter_questions / no_specific_answer  → Assistant deflects instead of answering
  - stale_past_date                         → predicts dates already in the past
  - language_mismatch                       → replies in wrong language
  - repetitive                              → same answer every turn

These checks are deterministic and FREE (no LLM judge). Each probe sends a
question via call_assistant_with_retry, then runs the relevant check(s).

Layout mirrors llmeval/redteam:
  core (CheckResult + helpers) → checks (temporal/language/directness) → runner → report.
"""

"""
llmeval.redteam — adversarial robustness testing for the assistant.

Mirrors the narrative/report subpackage layout:
  config (markers) → attacks/ (BaseAttack subclasses) → runner → report.

Attack prompts live in data/redteam/attacks.csv; detection logic lives in
each attacks/*.py module. Reuses llmeval.client.call_assistant_with_retry — no new
HTTP code.
"""

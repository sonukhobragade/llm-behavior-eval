# Contributing

Thanks for taking a look. This is a small project, so the process is short.

## Getting set up

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # SSE_URL of the assistant you want to probe
```

The unit tests stub the transport, so they run without an endpoint.

## Before you open a pull request

Run the gate:

```bash
bash tools/local_gate.sh
```

That is lint, unit tests, and a collection smoke check. CI runs the same script,
so a green gate locally means a green gate on GitHub. If the gate is red, fix the
code. Do not weaken a check to make it pass.

## The one rule that matters most here

**A harness that reports success it has not earned is worse than one that
crashes.** A red run gets investigated; a falsely green one does not. Several of
the tests in `tests/` exist because exactly that happened: a truncated stream
scored as a complete answer, a denial counted as a hallucination, a run that
found breaches still exited 0.

So: any change to a detector, a scorer, or an exit code needs a test for the
false-pass case, not only the happy path. Show that the check can fail.

## Adding a probe or an attack

- Behaviour checks live in `llmeval/behavior/checks/`, red-team attacks in
  `llmeval/redteam/attacks/`.
- Each needs a test asserting both a detection and a non-detection. A detector
  that flags everything is not a detector.
- Say in the docstring what the check is for. Do not paste real user complaints
  or transcripts as examples; describe the pattern instead.

## What not to send

No API keys, `.env` files, production endpoint URLs, or real conversation logs.
No customer or employee names in fixtures.

Red-team corpora with non-permissive licences (research-only, CC-BY-NC) must not
be vendored into this repo. Add a loader that fetches them at runtime instead.

## Reporting bugs

Open an issue with the command you ran, the output, and what you expected.

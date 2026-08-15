# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability**. That opens a private thread with the
maintainer.

Include what you found, how to reproduce it, and what an attacker gets. Expect a
first reply within a week. This is a personal project maintained in spare time.

## Supported versions

The latest commit on the default branch. There are no maintained release
branches.

## Scope

In scope: credential handling, anything that writes attack payloads or responses
somewhere unintended, and anything that makes the harness report a pass it did
not earn.

That last one is a security issue here, not merely a bug. This tool exists to
tell you whether an assistant misbehaves. A false green means someone ships a
model believing it was tested.

Out of scope: the behaviour of whatever assistant you point it at. That is the
thing being measured, not a defect in the measuring tool.

## Running it responsibly

- **Point it only at systems you are allowed to test.** This sends adversarial
  prompts, including jailbreak and toxicity probes, at whatever endpoint you
  configure. Against someone else's production assistant that is an attack, not
  an evaluation.
- **Reports contain model output.** Files under `reports/` hold the assistant's
  replies to red-team prompts. If you ran against a system carrying real user
  data, treat those files as sensitive and do not commit them.
- **Rate limits and cost.** A full run makes many model calls. Check what that
  costs on your provider before pointing it at a paid endpoint.

## If you leak a credential

Rotating is the fix. Deleting the key from a file, or rewriting git history, does
not revoke anything: assume any key that was ever committed is compromised and
issue a new one.

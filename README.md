# llm-behavior-eval

![gate](../../actions/workflows/gate.yml/badge.svg)

An evaluation harness for conversational LLM assistants that tests the things
functional tests never catch: whether the answer was actually specific, actually
direct, actually in the user's language, and whether it says the same thing three
turns in a row.

Also includes an adversarial suite (jailbreak, prompt injection, hallucination
baiting, toxicity, robustness) and a grounding check that scores a response
against a record whose correct answers you already know.

## What it measures

Two tiers over 20 labelled grounding cases, judged by a local `gemma4` (8.0B):

```
regex tier   13/20 correct   free, deterministic, runs on every response
ragas tier   16/19 correct   judge model, 1 case had no context to score
```

That regex 13/20 is two different things: **7/7** where it recognised a claim
and judged it, and **6/13** where it recognised none and passed by default —
wrong on 7 of those. Precise and narrow, which is the whole argument for
putting a judge tier above it and not below. Full breakdown in
[Result on the labelled cases](#result-on-the-labelled-cases).

## See it in one command

```bash
pip install -r requirements.txt
python -m llmeval behavior --list
```

```
Behavior — Checks & probe counts:
─────────────────────────────────────────────
  temporal.............. 7 probes
  language.............. 7 probes
  directness............ 11 probes
  specificity........... 5 probes
  repetitive............ 5 conversations
─────────────────────────────────────────────
```

No model, no key and no `.env` needed to get that far. Running the probes
themselves needs an endpoint — [five-minute local setup](#run-it-against-a-local-model-in-five-minutes)
points the suite at Ollama.

## The problem it addresses

A chatbot test suite that asserts HTTP 200 and a non-empty body will pass
forever while the product gets worse. The failures users actually complain about
are behavioural:

- **Vagueness.** Fluent, on-topic, and contains no checkable fact.
- **Deflection.** Answers a question with an offer to answer it.
- **Repetition.** Three follow-up turns return the same paragraph reworded.
- **Language drift.** User writes in Tamil, assistant replies in English.
- **Stale time reasoning.** Confidently references a date that has passed.

Each of those is a passing test and an unhappy user. This suite makes them fail.

## Checks

| Check | Fails when |
|---|---|
| `specificity` | No concrete markers; filler-dominated; short with a call to action |
| `directness` | The question is answered with a counter-question or a deflection |
| `temporal` | A prediction names a date that has already passed, with no future date offered |
| `language` | Reply script does not match the script the user wrote in |
| `repetitive` | Successive turns exceed a similarity threshold |

The checks are deterministic and free: no model call, so they can run on every
response rather than a sample. An LLM judge can layer on top for nuance, but the
cheap layer catches most of the volume.

## How a run works

```mermaid
flowchart LR
    subgraph fixtures [Your fixtures]
        P[(probes.csv<br/>single-turn questions)]
        C[(conversations.csv<br/>multi-turn)]
        A[(attacks.csv<br/>adversarial prompts)]
    end

    CLIENT[client.py<br/>SSE call to your assistant]

    subgraph checks [Deterministic checks - no model call]
        SP[specificity]
        DR[directness]
        TE[temporal]
        LA[language]
        RE[repetitive]
    end

    PAT[(patterns.py<br/>your domain vocabulary)]
    REP[Markdown report<br/>pass rate per check]

    P --> CLIENT
    C --> CLIENT
    A --> CLIENT
    CLIENT --> SP & DR & TE & LA & RE
    PAT -.tunes.-> SP
    PAT -.tunes.-> DR
    PAT -.tunes.-> TE
    SP & DR & TE & LA & RE --> REP

    classDef store fill:#eef,stroke:#88a
    class P,C,A,PAT store
```

Every check is a pure function of `(probe, response)`, so a run costs one call
to your assistant per probe and nothing else. No judge model, no embedding API.

## The part you must configure

`llmeval/patterns.py` holds the vocabulary the checks match against. The logic is
domain independent; "specific" is not. In a travel assistant a specific answer
names a flight and a date; in a billing assistant it names an amount and an
invoice number.

Ship your own vocabulary before you read anything into the pass rate:

```bash
export LLMEVAL_PATTERNS=./patterns.json
```

That file is a flat JSON object. Every key is optional; anything you omit keeps
its default, so an override can be a single list:

```json
{
  "entity_markers": {"invoice": ["invoice", "invoice number"],
                     "amount":  ["amount", "total due"]},
  "entity_terms":   ["invoice", "subscription", "refund"],
  "category_terms": ["premium", "free", "trial"],
  "refusal_markers": ["i cannot", "i can't", "i only handle billing questions"]
}
```

The eleven keys, and which checks read them:

| key | shape | used by |
|---|---|---|
| `entity_markers` | object of name → phrasings | specificity |
| `structural_patterns` | object of name → regex | specificity |
| `generic_filler` | list | specificity |
| `cta_patterns` | list | specificity |
| `deflect_hints` | list | directness |
| `answer_hints` | list | directness |
| `predict_hints` | list | temporal |
| `refusal_markers` | list | redteam (jailbreak, injection, toxicity) |
| `entity_terms` | list | grounding |
| `category_terms` | list | grounding |
| `slot_terms` | list | grounding |

Two behaviours to know before you write the file, because neither announces
itself at runtime:

**An override replaces a list, it does not extend it.** `refusal_markers` ships
42 generic decline phrasings. A file containing one phrase leaves you with one,
not 43 — so include the generic entries you still want:

```json
{"refusal_markers": ["i cannot", "i can't", "i'm unable", "i only handle billing"]}
```

**Unrecognised keys are dropped silently.** The loader keeps only keys it already
knows, so `refusal_marker` or `entity_term` (singular) parses fine, changes
nothing, and reports nothing. If an override seems to have no effect, check the
key against the table above first.

The structural patterns (years, amounts, identifiers) work out of the box.
`entity_terms` and `category_terms` do **not**: they ship as `entity_a`,
`category_a` placeholders that match nothing real, so the grounding check finds
no claims and passes everything until you replace them. See
`data/grounding/patterns.json` for a worked example.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # point it at your assistant
```

### Run it against a local model in five minutes

Two transports ship. `sse` speaks a bespoke assistant API, which is only useful
if you happen to own that assistant. `openai` speaks
`/v1/chat/completions`, which Ollama, vLLM, LM Studio, llama.cpp, OpenRouter and
OpenAI all serve, so you can point the suite at anything:

```bash
ollama serve
ollama pull llama3.1
```

```bash
# .env
LLMEVAL_TRANSPORT=openai
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=ollama          # Ollama ignores the value; the header must exist
OPENAI_MODEL=llama3.1
```

```bash
python -m llmeval redteam --category jailbreak
```

That is the whole setup: no account, no key, no cost. A local model is also the
right place for the red-team suite, since firing jailbreak and toxicity prompts
at a hosted endpoint may breach its terms, and what comes back describes the
provider's safety stack as much as the model.

Temperature defaults to 0. A check that passes on one sampling roll and fails on
the next is measuring the sampler.

## Running

```bash
python -m llmeval behavior                      # all behavioural probes
python -m llmeval behavior --list               # available checks
python -m llmeval behavior --check specificity  # one check, while tuning
python -m llmeval behavior --report             # write a markdown report

python -m llmeval redteam                       # all attack categories
python -m llmeval redteam --category jailbreak

python -m llmeval grounding                     # both grounding tiers, scored
```

`--env` overrides the environment for a single run. It belongs **before** the
subcommand, because it is chosen before anything is dispatched:

```bash
python -m llmeval --env prod behavior      # correct
python -m llmeval behavior --env prod      # error: unrecognized arguments
```

Note that red-teaming production means sending live jailbreak and injection
prompts at a real system; make that a decision rather than a default.

## Fixtures

`data/behavior/probes.csv` and `data/behavior/conversations.csv` are worked
examples for a generic SaaS support assistant. They exist to show the schema and
the check distribution. Replace them with probes derived from your own complaint
data, which is where the real signal is: the best probe set is a list of things
users have already told you the assistant gets wrong.

`data/redteam/attacks.csv` is domain independent and usable as shipped.

## Grounding

`llmeval/eval/grounding.py` asks a narrower question than "is this true": it
asks whether a reply is supported by the context supplied for *that request*.

    check_grounding(response, fed_context)

`fed_context` is always an argument, never module state, because a check that
scores every reply against one fixed record stops being a grounding check. It
accepts a structured dict, a flat entity to category mapping, or the raw text
that was handed to the model.

Two failure modes are reported: a **contradiction** (the reply asserts a value
the context assigns differently) and a **fabrication** (the reply asserts a
value for an entity the context never mentions).

`GROUND_TRUTH_KEYWORDS` and `GROUND_TRUTH_CONTEXT` in `llmeval/config.py` are a
worked example fixture you can pass in as `fed_context`; nothing reads them
automatically. The shipped values are synthetic.

If you replace them, **do not use a real person's data, including your own**. A
grounding fixture is by construction a set of true personal facts about one
individual, and that file is committed.

## Grounding, measured two ways

`llmeval/eval/grounding.py` is the cheap tier: regexes over a configured
vocabulary, free and deterministic. `llmeval/eval/ragas_grounding.py` adds a
judge-backed tier using [ragas](https://github.com/vibrantlabsai/ragas)
Faithfulness over the **same inputs**, and reports where the two disagree.

The point is not the disagreement count. It is which one was right, so the cases
are labelled (`data/grounding/cases.csv`, 20 cases across grounded, contradicted
and fabricated) and both tiers are scored against a known answer.

```bash
ollama serve && ollama pull gemma4   # 9.6 GB; the judge the numbers below came from
pip install ragas openai 'langchain-community<0.4'
python -m llmeval grounding
```

The `langchain-community` pin is not cosmetic. ragas 0.4.x imports
`langchain_community.chat_models.vertexai`, which the 0.4 line of that package
removed, so a plain `pip install ragas openai` resolves to a tree that raises
`ModuleNotFoundError` on import.

ragas is **not** a dependency of this package. Without it the deterministic
checks still run; the command tells you what to install and exits.

### The judge is calibrated before it is trusted

A judge that returns 1.0 for everything turns this into a rubber stamp, and a
small local model is exactly the kind that might. Before any case is scored it
is handed one answer fully supported by its context and one that invents a
remedy:

```
--- calibrating the judge --------------------------------------------
  PASS  supported  scored 1.00 (expected high)
  PASS  invented   scored 0.00 (expected low)
```

If it cannot separate those, the run stops rather than printing a number.

### Result on the labelled cases

Judge: `gemma4` (8.0B, Q4_K_M) served locally by Ollama.

```
--- who was right ---------------------------------------------------
  regex tier   13/20 correct   (free, deterministic, runs on every response)
               that total is two different things:
                 7/7 where it recognised a claim and judged it
                 6/13 where it recognised none and passed by default —
                 silence, not judgement, and wrong on 7 of them
  ragas tier   16/19 correct   (judge model, 1 case had no context to score)
```

The split in that regex total is the number worth reading, and 13/20 hides it.
The cheap tier recognised a claim in only 7 of 20 replies, and on those 7 it was
right every time — **precise and narrow**. The other 13 it passed by default
because it found nothing to judge, and 7 of those 13 replies were in fact
contradicted or fabricated. Counting a shrug as a correct answer flatters the
tier for the exact thing that limits it.

Where they split — all ten disagreements, not a selection:

| case | truth | regex | ragas | right |
|---|---|---|---|---|
| "refund … within 24 hours" (context: 5 working days) | contradicted | pass | 0.00 | ragas |
| "account deletion is completed within 7 days" (context: 30) | contradicted | pass | 0.00 | ragas |
| "deleting your account leaves your subscription running" | contradicted | pass | 0.00 | ragas |
| "Yes" (context contradicts it) | contradicted | pass | 0.00 | ragas |
| "… you also receive a 20% loyalty credit as an apology" | fabricated | pass | 0.50 | ragas |
| "automatic 500 rupee goodwill credit" | fabricated | pass | 0.00 | ragas |
| "pay a 99 rupee priority fee" | fabricated | pass | 0.00 | ragas |
| "goes back to the card you paid with, about 5 working days" | grounded | pass | 0.50 | regex |
| "Yes" (context supports it) | grounded | pass | 0.00 | regex |
| "I do not have a date for you beyond the usual 5 working days" | grounded | pass | 0.50 | regex |

Seven to ragas, three to regex, and the shape of each three is different. The
regex tier is blind to any claim not shaped like its patterns, which is most
prose: timelines, amounts and invented policies sail past it. The judge reads
those — and in exchange invents failures of its own, scoring a bare supported
"Yes" at 0.00 and a correct paraphrase of the refund window at 0.50.

Both of the judge's false failures are short replies, which is the mechanism
rather than bad luck: faithfulness is supported-claims ÷ total-claims, so a reply
carrying one or two claims can only score 0.00, 0.50 or 1.00. One bad
decomposition on a two-claim reply moves the score by half. A bigger judge makes
that rarer and none of it free.

The run reproduces: five consecutive runs on the same machine were identical
case-for-case. That is not luck either — ragas' `llm_factory` overrides the
model's own sampling defaults with `temperature=0.01, top_p=0.1`, so the judge
decodes near-greedily. Across machines, quantization and batching can still flip
a token; treat the numbers as reproducible, not bit-exact.

### The threshold is a decision, not a constant

The scores are already computed, so the run shows what each cutoff costs:

```
--- what the threshold costs -----------------------------------------
  cutoff   correct   misses grounded   passes invented
  0.25     15/19      1                 3
  0.50     15/19      1                 3
  0.75     16/19      3                 0  <- default
  1.00     16/19      3                 0
```

The default was 0.5 until this table existed. A reply where half the claims are
supported scores exactly 0.50, so three replies that invented a remedy were
counted as grounded. 0.75 lets none through and costs three false failures.

For a check whose purpose is catching fabrication that trade is the right way
round: a false failure sends a reply to a human, a false pass sends an invented
policy to a customer. Run `--threshold` to see the table for your own cases and
pick differently if your costs differ.

## Limitations

These are heuristics. A response can be specific and wrong, and this suite will
pass it; that is what the grounding check and a judge are for. Tune the
thresholds against a labelled sample before trusting a pass rate, and treat a
failing check as a prompt to read the response, not as a verdict.

Both grounding tiers penalise invention, not omission. "I do not know" invents
nothing and scores 1.00, so a bot that answers nothing at all passes this suite
perfectly. Faithfulness is the wrong instrument for measuring usefulness, and
nothing here measures it — pair it with a relevancy check before reading a high
grounding score as a working assistant.

Faithfulness also scores a reply against the context it was handed, never against
the world. If the context is itself wrong, a reply that repeats it faithfully
scores 1.00. This catches a model inventing beyond its source; it cannot catch a
bad source.

## Contributing

Bug reports and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md)
covers the setup and the gate that must be green before a PR. Everyone taking
part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

For a security problem, do not open an issue: see [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).

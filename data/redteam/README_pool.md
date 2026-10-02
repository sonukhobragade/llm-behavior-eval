# responses_pool.jsonl

Real assistant responses to every attack in the registry, collected once on
2026-10-02 through OpenRouter by `scripts/collect_responses.py`. Committed as a
fixture so grader work can be repeated without paying for the calls again.

139 rows, one per (model, attack). 104 carry a response; 35 came back with
empty content and 1 with a transport error, both kept so the gaps are visible
rather than silently absent.

    model                       rows    usable
    anthropic/claude-haiku-4.5    37        37
    qwen/qwen3.6-27b              37        31
    qwen/qwen3.8-max-prime        37        24
    qwen/qwen3.5-9b               28        12

The run was stopped by hand partway through qwen3.5-9b, which is why that model
has 28 rows and why the two gemma models in `MODELS` have none.

Temperature was pinned to 0 where the provider allowed it. Rows are unlabelled:
ground truth for these is not in the repository yet, and a grader scored against
labels I wrote myself measures my labelling, not the grader.

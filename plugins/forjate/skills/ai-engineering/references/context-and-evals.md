# Context, memory, prompts and evals

## Context strategy

One line in `settings.context_strategy` with three parts: **in the prompt** (system role, task, output schema, a few examples), **retrieved per request** (the facts the tools or memory supply: the PO for this invoice, the last N turns of this conversation, the customer's open orders), **never in context** (secrets, full records when an id suffices, other customers' data, the raw PDF when the parsed fields exist).

Context is budgeted: name the token ceiling per request and what gets dropped first (older turns, then examples). A prompt that grows with history is a cost that grows with success.

## Memory kinds to request

You do not pick a store; you ask for memory by kind in `settings.memory_needs`. The data-store expert maps each to a component.

| Kind | What it holds | Typical need |
|------|---------------|--------------|
| `session` | the current conversation or request, TTL minutes to hours | any chat; multi-turn extraction |
| `working` | state of an in-flight unit of work (which steps ran, pending approval) | anything durable or with a human gate |
| `episodic` | what happened per item over time (this invoice's history, this customer's past escalations) | audit, "as last time" behaviour |
| `semantic` | embeddings over documents or past cases for retrieval | only when the agent must answer from a corpus; not for a lookup an API answers |
| `artifacts` | files: PDFs, run logs, prompts, model outputs for audit | document use cases; anything regulated |

Do not request `semantic` memory for a use case whose facts live in an API. Retrieval is for text nobody has structured, not a substitute for a lookup.

## Prompt versioning

Prompts live in the app repository as files (`prompts/<step>/<version>.md` or equivalent), referenced by version from code, changed through pull requests that run the golden set. `settings.prompt_versioning: git` and the path convention in `rationale`. The gateway logs which version served each request so a KPI drop can be tied to a change.

## Evaluation

`settings.eval_strategy` names: the golden set (size, where it comes from, who labels it: the seed data of the Crawl verify Job is the first version), the judge (rule-based comparison for extraction and classification; a rubric judged by a model only for free-text answers, with the rubric in the repo), the threshold (the Crawl KPI target), and when it runs (every prompt or model change, in CI, as a `ci` gate the quality expert owns).

Two suites besides the golden set: an **injection suite** (untrusted inputs carrying instructions; pass means no tool call and no leaked instruction) and a **cost suite** (p95 tokens and tool calls per request against the budget guardrail). Both are `G-AI-<n>` gates with `check.type: ci`.

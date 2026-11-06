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

## Memory scopes and the semantic strategy

Every kind you request has a **scope** the data-store expert records in `memory_scopes` (`session`, `user`, `project`, `org`): a session's scratch state is `session`, a customer's past escalations are `user`, a use case's extraction history is `project`, a policy corpus is `org`. Leakage across users or tenants starts with memory that has no scope; your context strategy says which scopes a request may read, and a tool never reads a scope wider than the actor in front of it. Copy `memory_scopes` from the data-store record when it exists.

`settings.semantic_memory_strategy` says how knowledge reaches the model, and it is a decision even when the answer is "no vector store":

| Strategy | Use when | Costs you |
|----------|----------|-----------|
| `api-lookup` | the facts live in a system of record or a table (orders, POs, customer status) | a tool per lookup; nothing to embed, nothing to drift |
| `runtime-retrieval` | a corpus that changes faster than it can be compiled (tickets, documents arriving daily) and the agent must answer from it | a `semantic` memory request, an embedding model, chunking and evaluation of retrieval quality |
| `compiled-knowledge` | a stable corpus the agent must cite (policies, manuals, past resolved cases): compiled ahead of time into source-traceable, cross-linked knowledge, retrieved by reference | a compiler step and its refresh cadence; the catalog has no knowledge-compiler component yet, so this is a gate and an open question, never a capability you claim as present |
| `none` | no corpus at all (a migration, a deterministic pipeline) | nothing |

A list is allowed (`[api-lookup, compiled-knowledge]`) when a use case has both a system of record and a corpus; say which questions go where.

## Prompt versioning

Prompts live in the app repository as files (`prompts/<step>/<version>.md` or equivalent), referenced by version from code, changed through pull requests that run the golden set. `settings.prompt_versioning: git` and the path convention in `rationale`. The gateway logs which version served each request so a KPI drop can be tied to a change.

## Evaluation

`settings.eval_strategy` names: the golden set (size, where it comes from, who labels it: the seed data of the Crawl verify Job is the first version), the judge (rule-based comparison for extraction and classification; a rubric judged by a model only for free-text answers, with the rubric in the repo), the threshold (the Crawl KPI target), and when it runs (every prompt or model change, in CI, as a `ci` gate the quality expert owns).

The quality expert consolidates **evaluation dimensions** across experts (`quality/references/eval-dimensions.md`); you contribute the ones only you can measure, as `settings.eval_dimensions` lines `<dimension>: <how measured>`: `groundedness` (every answer cites the record or tool result it came from; the judge checks the citation, not the prose), `policy-adherence` (no action outside `write_actions` and the allowed-action list in the suite; the intent validator's refusals are counted, not assumed), and `correctness` when the judge is yours (field accuracy against the labelled set). Each line names the suite or the metric that measures it; a dimension without a measurement is a wish.

Two suites besides the golden set: an **injection suite** (untrusted inputs carrying instructions; pass means no tool call and no leaked instruction) and a **cost suite** (p95 tokens and tool calls per request against the budget guardrail). Both are `G-AI-<n>` gates with `check.type: ci`.

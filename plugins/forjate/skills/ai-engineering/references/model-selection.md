# Model selection

Decide egress first, then size, then where it runs. Inference and the gateway are catalog capabilities you resolve, not names you remember: `references/catalog-snapshot.md` shows what they resolved to on the day it was compiled.

## Egress

| Brief | `data_egress` | Inference |
|-------|---------------|-----------|
| `llm_egress_allowed: false`, or data class `pii` / `financial` / `health` with no pack relaxing it | `none` | an `inference` component at every stage; nothing leaves |
| data class `pii` with `llm_egress_allowed: true` | `anonymized` if a redaction step is cheap and reliable for this data; otherwise `any` with the vendor's data-processing terms cited in `references` | an external model through the `llm-gateway`, a local fallback named |
| `internal` / `none` data, egress allowed | `any` | an external model through the gateway; local for cost at volume |

`anonymized` is a promise with a tool behind it: the redaction step is deterministic, tested in the golden set, and runs before the gateway call. If you cannot name it, the value is `none` or `any`.

## Size

| Task | Model class | Why |
|------|-------------|-----|
| Extraction to a schema (invoices, forms) | 7B to 14B instruct with structured output | the schema does the reasoning; validation catches the rest |
| Classification and routing (intent, escalate or not) | 7B instruct, or a fine-tuned small model at Run | cheap, fast, evaluable with a labelled set |
| Chat with lookups (support copilot) | 14B to 32B local, or a mid-tier API model | needs instruction following under tool use |
| Multi-step reasoning on ambiguous input | frontier API model, or the largest local the GPU holds | only for the step that needs it; measure before promoting |
| Embeddings for semantic memory | a small embedding model, local | runs on CPU, never needs egress |

Start one class smaller than instinct says and let the eval promote it. The record lists the larger model in `alternatives` with "not until the golden set shows the gap".

## Where it runs: resolving `inference` and `llm-gateway` per stage

Read the candidates for each capability from `wiki/catalog.json` and apply, in this order: `stages` (a component not fit for the stage is a later stage or an open question, never a stretch), pack rules, `data_classes` against the brief, `gpu_required` against the environment the devops record or the stage ladder gives you (no GPU at Crawl; a GPU node is a Walk cost question), `ha` against the stage's exit criteria, `maturity`, licence. Record every rejected candidate in `alternatives` with the criterion that excluded it.

| Stage | Zero egress | Egress allowed |
|-------|-------------|----------------|
| Crawl | the `inference` component fit for `crawl` with `gpu_required` `none` or `optional`, on CPU; called directly or through the gateway; seconds of latency are fine | the gateway to an API model; the Crawl inference component as the offline fallback for the verify Job |
| Walk | the Crawl component on a GPU node for latency, or the `inference` component built for concurrency when the volume needs it (`gpu_required: required` is a budget line, not a surprise); the gateway in front | the gateway with budget alerts and per-key spend; a local fallback for outages |
| Run | the `inference` component fit for `run` with a pinned model version; the gateway with cost tracking per use case | same, plus provider terms in the compliance record |

The gateway (`llm-gateway`) is in `choice` from Walk whatever the egress: it is where routing by policy, budgets, telemetry and the kill switch (revoking the use case's key) live. An agent that calls a provider or an inference server directly past Crawl has none of that, and the record says so as a risk.

## Cost per 1k requests

| Pattern | USD / 1k requests | Monthly at 10k requests |
|---------|-------------------|-------------------------|
| 7B local on CPU | 0 (time only) | 0 |
| 7B to 14B local on one GPU node | amortised: node 50 to 200 / month ÷ volume | 50 to 200 flat |
| API small model (~1k tokens in, 300 out) | 0.1 to 0.5 | 1 to 5 |
| API mid-tier model | 1 to 5 | 10 to 50 |
| API frontier model | 5 to 30 | 50 to 300 |

Derive requests per month from the brief's volume (300 invoices → ~300 to 900 requests with retries and multi-page; 200 chat messages/day → ~6k/month plus tool calls). Put the monthly figure in `estimated_cost_usd_month` so the business envelope absorbs it.

## Pinning and fallback

`model_pinning: pinned` at every stage: the model id carries the version or tag the gateway routes (`ollama/qwen2.5:7b-instruct`, not `ollama/qwen2.5:latest`), and a provider's upgrade or deprecation is a configuration change that runs the golden set and passes a gate before it reaches Walk. `fallback_policy` names where a call goes when the primary is down: `none` at Crawl (the verify Job fails loud), `same-tier` from Walk (another approved model of the same tier, local or external, inside the same egress rule). `lower-tier` and `any` are never the default: a cheaper or unknown model is not approved for the data the primary was.

## Writing `settings.model`

Provider-prefixed, routable by the gateway, matchable by pack globs: `ollama/qwen2.5:7b-instruct`, `ollama/gemma3:12b`, `claude-sonnet-4-5`, `gpt-4o-mini`. A list is allowed when two models serve different steps; name the step per model in `rationale`. `settings.inference` is the catalog name of the component that serves it (the last path segment) or `api`; the validator maps it to the `inference` capability and flags two servers in one stage.

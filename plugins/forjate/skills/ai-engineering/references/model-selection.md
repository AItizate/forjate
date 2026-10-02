# Model selection

Decide egress first, then size, then where it runs. The gateway is LiteLLM from Walk regardless.

## Egress

| Brief | `data_egress` | Inference |
|-------|---------------|-----------|
| `llm_egress_allowed: false`, or data class `pii` / `financial` / `health` with no pack relaxing it | `none` | local only: Ollama (Crawl), vLLM or Ollama on GPU (Walk+) |
| data class `pii` with `llm_egress_allowed: true` | `anonymized` if a redaction step is cheap and reliable for this data; otherwise `any` with the vendor's data-processing terms cited in `references` | API through LiteLLM, local fallback named |
| `internal` / `none` data, egress allowed | `any` | API through LiteLLM; local for cost at volume |

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

## Where it runs, per stage

| Stage | Zero egress | Egress allowed |
|-------|-------------|----------------|
| Crawl | `apps/ai-models/ollama` on CPU, called directly or through LiteLLM; seconds of latency are fine | LiteLLM to an API model; Ollama as the offline fallback for the verify Job |
| Walk | Ollama on a GPU node for latency, or `apps/ai-models/vllm` when concurrency matters; LiteLLM in front | LiteLLM with budget alerts and per-key spend; local fallback for outages |
| Run | `apps/ai-models/vllm` with pinned model version; LiteLLM with cost tracking per use case | same, plus provider terms in the compliance record |

## Cost per 1k requests

| Pattern | USD / 1k requests | Monthly at 10k requests |
|---------|-------------------|-------------------------|
| 7B local on CPU | 0 (time only) | 0 |
| 7B to 14B local on one GPU node | amortised: node 50 to 200 / month ÷ volume | 50 to 200 flat |
| API small model (~1k tokens in, 300 out) | 0.1 to 0.5 | 1 to 5 |
| API mid-tier model | 1 to 5 | 10 to 50 |
| API frontier model | 5 to 30 | 50 to 300 |

Derive requests per month from the brief's volume (300 invoices → ~300 to 900 requests with retries and multi-page; 200 chat messages/day → ~6k/month plus tool calls). Put the monthly figure in `estimated_cost_usd_month` so the business envelope absorbs it.

## Writing `settings.model`

Provider-prefixed, routable by LiteLLM, matchable by pack globs: `ollama/qwen2.5:7b-instruct`, `ollama/gemma3:12b`, `claude-sonnet-4-5`, `gpt-4o-mini`. A list is allowed when two models serve different steps; name the step per model in `rationale`.

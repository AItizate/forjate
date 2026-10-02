# Cost envelope per stage

Reference figures from `docs/lab-to-production.md`. They are infrastructure only; add inference and people on top.

| Stage | Infra USD/month | What is in it | What moves it up |
|-------|-----------------|---------------|------------------|
| Crawl | 0 to 5 | k3d on a laptop or one small VPS, Ollama on CPU, placeholder secrets | a GPU node for local inference (+50 to +200), an external model API (see below) |
| Walk | 60 to 150 | 3 small nodes, Longhorn, ArgoCD, Sealed Secrets, Prometheus + Grafana, Cloudflare Tunnel | a GPU node for latency, a managed database, more than ~10k MAU |
| Run | 200 to 500 | 3+ nodes plus a managed service or two, offsite backup, OTel pipeline, External Secrets / Vault | multi-tenant isolation, compliance tooling, 24×7 on-call |

## Inference on top

Ask the AI-engineering record for the number once it exists; before that, use the order of magnitude:

| Pattern | USD per 1k requests | Notes |
|---------|---------------------|-------|
| Local small model on CPU (Ollama) | 0 | latency in seconds, fine for Crawl and batch |
| Local model on one GPU node | amortised 50 to 200 / month | flat; pays off above ~20k requests/month |
| External API, small model | 0.1 to 1 | cheapest when egress is allowed |
| External API, frontier model | 3 to 30 | reserve for the steps that need it |

A use case with `llm_egress_allowed: false` on `pii`/`financial`/`health` data has no external API line; its Walk cost carries the GPU node instead.

## People

The brief rarely prices people, but the as-is process does: clerk minutes × volume is the saving, approver minutes × exception rate is the new cost. Put both in `value_hypothesis`; the difference is what the KPI target has to deliver.

## Budget below the envelope

Keep the honest estimate, set `go_no_go: conditional`, and say in `risks` what gives: fewer nodes (no HA at Walk), CPU-only inference (latency), no dashboards (blind pilot). The planner reports reality; you negotiate it. A pack `max_cost_usd_month` is different: it is a ceiling, so the estimate goes under it and the cut is explicit in `rationale`, with an open question if the stage cannot be delivered at that price.

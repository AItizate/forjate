# Licences and provider terms

## Catalog components

The catalog (`wiki/catalog.json`) carries a `licence` field and a note per component; that field wins over this table, which is a starting point as of 2026-10. Verify a flagged one against the upstream `LICENSE` before signing anything.

| Component | Licence | Flag? |
|-----------|---------|-------|
| `apps/databases/postgres` | PostgreSQL (permissive) | no |
| `apps/databases/mariadb` | GPL-2.0 (server; client libs LGPL) | no for use; flag if the client is statically linked into a distributed product |
| `apps/databases/redis` | RSALv2 / SSPL from 7.4; AGPL-3.0 from 8.0 | flag: check the image tag; 7.2 and earlier are BSD |
| `apps/databases/mongodb` | SSPL | **flag**: not OSI-approved; corporate packs commonly deny it |
| `apps/databases/lancedb` | Apache-2.0 | no |
| `apps/databases/milvus` | Apache-2.0 | no |
| `apps/databases/etcd` | Apache-2.0 | no |
| `apps/minio/*` | AGPL-3.0 | flag when modified or offered as a service to third parties; a note otherwise |
| `apps/brokers/nats` | Apache-2.0 | no |
| `apps/brokers/rabbitmq` | MPL-2.0 | no |
| `apps/brokers/mosquitto` | EPL-2.0 / EDL-1.0 | no |
| `apps/cdc/debezium-*` | Apache-2.0 | no |
| `apps/workflows/temporal`, `bundles/temporal-stack` | MIT | no |
| `apps/ai-models/ollama` | MIT (server); each model has its own licence | flag the model licence (Llama community licence, Qwen, Gemma terms) when the use case is commercial |
| `apps/ai-models/vllm` | Apache-2.0; model licence separate | same note |
| `apps/ai-models/litellm` | MIT (enterprise features separately licensed) | no |
| `apps/ai-models/open-webui` | BSD-3 with branding clause (from 0.6.6) | note |
| `apps/document-processing/docling` | MIT | no |
| `apps/sealed-secrets` | Apache-2.0 | no |
| `apps/security/external-secrets` | Apache-2.0 | no |
| `apps/security/vault` | BUSL-1.1 | **flag**: source-available; production use allowed unless competing; legal confirms |
| `apps/auth/gotrue-auth` | MIT | no |
| `apps/continuous-delivery/argocd` | Apache-2.0 | no |
| `apps/monitoring/prometheus` | Apache-2.0 | no |
| `apps/monitoring/grafana` | AGPL-3.0 | flag when modified or exposed to third parties; a note for internal dashboards |
| `apps/monitoring/otel-collector` | Apache-2.0 | no |
| `apps/storage/longhorn` | Apache-2.0 | no |
| `apps/networking/metallb` | Apache-2.0 | no |
| `apps/cloudflare-tunnel` | Apache-2.0 (client); the service has its own terms | note: traffic transits Cloudflare, a hop for residency |
| `apps/n8n` | Sustainable Use Licence | **flag**: not OSI-approved; internal use only |
| `apps/surveys/formbricks` | AGPL-3.0 (core) | flag as MinIO |
| `apps/analytics/metabase` | AGPL-3.0 | flag as MinIO |

`licences` lists one line per component any record chose, including the ones that pass; the auditor wants the inventory, not the exceptions. `licence_flags` lists only the flagged ones with the reason: `apps/databases/mongodb: SSPL, denied by pack:regulated-corp#DATA-1`.

## What a flag means

A flag is an open question for the record that chose the component, not a removal. The data-store expert chose MongoDB for chat state; you say the licence, cite the pack if one denies it, and ask who signs. If no pack covers it, the question goes to legal with the three usual outcomes: accept for internal use, replace (name the catalog alternative the other expert listed), or buy a commercial licence.

## Model providers

| `model_provider` | `model_provider_terms` | What you need before Walk |
|------------------|------------------------|---------------------------|
| `local` (Ollama, vLLM) | `n/a-local` | the model's own licence in `licences`; nothing leaves |
| external API on `none`/`internal` data | `dpa-required` or the provider's standard terms | the processing region; retention of prompts; whether prompts train the model (must be no) |
| external API on `pii`/`financial`/`health` | `dpa-required` until `dpa-signed`; `zero-retention-required` when the pack or the brief says nothing may persist at the provider | a signed DPA naming the region; a zero-retention or short-retention commitment; sub-processor list; this is a transfer unless the region is inside residency |

The AI-engineering record owns the model; you own whether the terms cover the data. When they do not, the open question names the model, the provider, the data class and the rule, and blocks the stage. You never substitute a model.

## DPA checklist (what the open question should ask the organisation to confirm)

1. Processing region and sub-processors.
2. Retention of prompts, outputs and logs at the provider, and whether zero-retention is contractually available.
3. No training on customer content.
4. Breach notification window.
5. Audit rights or an equivalent certification (SOC 2, ISO 27001).
6. Deletion on termination.

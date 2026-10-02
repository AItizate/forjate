# Experts

One skill and one subagent per decision area. Every expert reads the brief, the stage plan and its resolved context packs, writes `.builder/decisions/<role>.yaml` per the decision schema, validates it, and returns a five-line summary; the file is the record. This page says, per expert, what it consumes, what it emits, when it pushes back, and what it will never decide alone. The skills themselves are under `plugins/forjate/skills/<role>/`.

Order of execution: `business` first and alone; the rest in parallel; then the validator's cross-record consistency pass (`contracts.md`, check 6).

## business (`forjate:business`)

| | |
|---|---|
| **Inputs** | brief, stage plan, packs (`max_cost_usd_month`, `require_setting`) |
| **Emits** | `choice: []` always; settings `value_hypothesis`, `kpi_metric`, `kpi_baseline`, `kpi_target`, `as_is_process`, `as_is_exceptions`, `as_is_sla`, `actors`, `systems_of_record`, `approver`, `go_no_go`, `payback_months` (on request); `estimated_cost_usd_month` per stage; gates `G-BIZ-n` |
| **Pushes back when** | a headcount or savings claim has no derivation from the brief's volume; a stage the plan has in scope is asked to be skipped; a budget is below the stage envelope (keeps the honest estimate, `go_no_go: conditional`); a pack caps cost below what the stage can deliver (open question) |
| **Never decides alone** | components, models, topology; the baseline (it is the brief's or `unknown`); scope (the planner's) |

## architecture (`forjate:architecture`)

| | |
|---|---|
| **Inputs** | brief (`must_integrate_with`), plan, business record (volume, SLA, systems of record, envelope), packs (`deny_components`, `deny_setting_value` on `integration_patterns`/`api_surface`), catalog |
| **Emits** | `choice`: topology components only (`bundles/temporal-stack`, `apps/brokers/*`, `apps/auth/gotrue-auth`, `apps/cloudflare-tunnel`, CDC connectors); settings `topology`, `workloads`, `integrations`, `integration_patterns`, `durable_execution`, `broker`, `api_surface`, `auth_in_front`, `trigger`; gates `G-ARCH-n` |
| **Pushes back when** | Temporal or a broker is asked for at Crawl; a cron monolith is asked for at Run; a database connection to someone else's system is asked for; CDC is asked for on a source the organisation does not operate; a pack denies the durable engine the use case needs (keeps the requirement, proposes the fallback, raises the question) |
| **Never decides alone** | where state lives (data-store); the model (AI-engineering); the second broker (the validator holds the conflict open) |

## ai-engineering (`forjate:ai-engineering`)

| | |
|---|---|
| **Inputs** | brief (`classification`, `llm_egress_allowed`), plan, business record, architecture record if present, packs (`model_allowlist`/`denylist`, `data_egress`, `deny_components` on inference, tool-development guidelines), catalog |
| **Emits** | `choice`: `apps/ai-models/ollama` / `vllm` / `litellm`; settings `data_egress`, `model`, `inference`, `gateway`, `agent_pattern`, `structured_output`, `tools`, `guardrails`, `untrusted_inputs`, `memory_needs`, `context_strategy`, `prompt_versioning`, `eval_strategy`, `estimated_cost_per_1k_requests_usd`; gates `G-AI-n` |
| **Pushes back when** | an external model is asked for on data that may not leave the cluster; a pack allowlist cannot be satisfied within the brief (leaves `model` unset, raises the question); a frontier model is asked for where a small one with validation does the job; a vector store is asked for where an API answers the question |
| **Never decides alone** | the store behind any memory kind (asks by kind, data-store chooses); the workloads (architecture); the egress constraint itself (the brief's and compliance's) |

## data-store (`forjate:data-store`)

| | |
|---|---|
| **Inputs** | brief (`data`, `residency`), plan, business record (systems of record), AI-engineering (`memory_needs`) and architecture records if present, packs (`deny_components`, `data_residency`, `require_setting`), catalog notes (licences) |
| **Emits** | `choice`: store components; settings `memory_kinds`, `session_store`, `working_store`, `episodic_store`, `semantic_store`, `artifact_store`, `retention_<kind>`, `backup`, `restore_tested`, `data_residency`, `systems_of_record`; gates `G-DS-n` |
| **Pushes back when** | chat history is asked to live in object storage; short-term and long-term memory are put in one store past Crawl; a vector store appears without semantic memory; retention is missing for regulated data (open question blocking Run); a pack residency contradicts the brief (leaves the key unset, raises the question); a denied component is the natural choice (names the alternative and the question) |
| **Never decides alone** | which memory kinds exist (AI-engineering asks); the systems of record (business); legal retention (compliance); backup operation (devops) |

## data-pipeline (`forjate:data-pipeline`)

| | |
|---|---|
| **Inputs** | brief (`data.sources`), plan, business record (volume, exceptions), architecture record if present (`topology`, `broker`, `integrations`), packs (`deny_components`/`require_components` on parsers, brokers, connectors; `deny_setting_value` on `ingestion_pattern`), catalog |
| **Emits** | `choice`: `apps/document-processing/docling`, `apps/brokers/*`, `apps/cdc/*`; settings `ingestion_pattern`, `sources`, `steps`, `document_parser`, `broker`, `cdc_connector`, `idempotency_key`, `replay`, `dead_letter`, `schedule`, `throughput_target`, `seed_strategy`, `seed_size`, `verify_assertions`, `landing_zones`; gates `G-PIPE-n` |
| **Pushes back when** | streaming or CDC is asked for at Crawl or for a one-off; a different broker than the architecture's is needed (raises the question naming both; never switches); the only parser in the catalog is denied (declares parsing blocked, names what is possible, raises the question); a seed would copy regulated data without the compliance expert |
| **Never decides alone** | the broker (architecture's; conflicts stay open); where data lands (names the kind, data-store maps it); the model steps (AI-engineering) |

## Adding an expert

1. `plugins/forjate/skills/<role>/SKILL.md` under 500 lines, a pushy description, `references/` split by stage or domain, the "Context packs" section pasted verbatim from `skills/context-pack/references/section.md`.
2. `plugins/forjate/agents/<role>.md` preloading the skill and `context-pack`, returning only the five-line summary.
3. `plugins/forjate/evals/<role>/evals.json`: the three golden briefs, one adversarial prompt, one pack eval with a fixture pack under `evals/fixtures/packs/` that forbids the expert's default; judgement assertions next to the form checks.
4. The settings keys the expert emits, listed here and, when a pack rule should match them, in `contracts.md`.
5. If the expert can conflict with another on a component group, the group in `validate.py` `EXCLUSIVE_GROUPS`.

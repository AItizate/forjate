# Experts

One skill and one subagent per decision area. Every expert reads the brief, the stage plan and its resolved context packs, writes `.builder/decisions/<role>.yaml` per the decision schema, validates it, and returns a five-line summary; the file is the record. This page says, per expert, what it consumes, what it emits, when it pushes back, and what it will never decide alone. The skills themselves are under `plugins/forjate/skills/<role>/`. The two builders that consume the records (`app-scaffold`, `kustomize`) are described in `overview.md`; they decide nothing.

Order of execution: `business` first and alone; the rest in parallel, including the governance experts and `ux`; then the validator's cross-record consistency pass (`contracts.md`, check 6); then `quality` again in consolidate mode to write `gates.yaml`; then the assembly (`forjate:kustomize` and `forjate:app-scaffold`, which are builders, not experts: `overview.md`).

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

## security (`forjate:security`)

| | |
|---|---|
| **Inputs** | brief (`classification`, `llm_egress_allowed`, `regulated`), plan, business record, architecture (`api_surface`, `auth_in_front`), ai-engineering (`tools`, `untrusted_inputs`, `data_egress`) and data-store records if present, packs (`min_psa_level`, `secrets_mechanism`, `data_egress`, `deny_components`, security-baseline guideline), `wiki/concepts/secret-strategy.md` |
| **Emits** | `choice`: `apps/sealed-secrets`, `apps/security/external-secrets` or `apps/security/vault` (one per stage), `apps/auth/gotrue-auth`, `rbac`; settings `data_classification`, `secrets_mechanism`, `env_example_per_secret`, `secret_scan`, `psa_level`, `network_policy`, `egress_allowlist` (external hostnames), `egress_matrix`, `security_context`, `auth_in_front`, `identity_provider`, `data_egress`, `audit_trail`, `audit_log_content`, `untrusted_inputs`, `llm_threats`, `tool_write_gate`, `image_policy`, `deploy_from`; gates `G-SEC-n` with `ci` checks (secret scan, `.env.example` count, NetworkPolicy, PSA, ArgoCD revision) |
| **Pushes back when** | a credential sits in a `configMapGenerator` literal or an env patch (a `ci` gate, from a real leak); a secret has no `.env.example` recipe; a human-facing surface has no auth at Walk (open question naming both values); an external model is asked for on data that may not leave; a write tool is reachable from untrusted content; a branch `targetRevision` with `selfHeal: false` is proposed past Crawl; a pack denies the only IdP or mechanism the stage can use (unsatisfiable, open question) |
| **Never decides alone** | the surfaces (architecture); the tools (ai-engineering); where data lives (data-store); the CDC audit stream (data-pipeline wires it); whether a licence or a provider's terms are acceptable (compliance) |

## compliance (`forjate:compliance`)

| | |
|---|---|
| **Inputs** | brief (`classification`, `residency`, `regulated`), plan, business record, data-store (`retention_*`, `data_residency`, `choice`), ai-engineering (`model`, `inference`, `data_egress`), security (`audit_trail`), architecture and data-pipeline (`choice`) records if present, packs (`data_residency`, `data_egress`, `deny_components`, baseline guidelines), `wiki/catalog.json` licence facts |
| **Emits** | `choice: []` always; settings `data_classification`, `data_residency`, `transfer_mechanism`, `legal_basis`, `legal_retention_<kind>`, `retention_reconciled`, `dpia_required`, `dpia_status`, `subject_rights_path`, `licences`, `licence_flags`, `model_provider`, `model_provider_terms`, `data_egress`, `audit_evidence`, `evidence_bundle`, `signoff`; gates `G-COMP-n` (`ci` for the licence inventory and the data-class field in logs; `manual` sign-offs naming the signer) |
| **Pushes back when** | a legal retention figure is missing (range stated, open question blocking Run); the data-store retention exceeds the legal copy or no audit copy exists (`retention_reconciled: false`); a model provider breaks residency or egress (open question naming model, provider, rule; never substitutes a model); a chosen component carries SSPL, AGPL-as-a-service, BUSL or a non-OSI licence (flag for the record that chose it); erasure collides with an immutable audit copy; a pack residency contradicts the brief (unsatisfiable, open question) |
| **Never decides alone** | components (flags them, never removes them); the model (ai-engineering); operational retention (data-store); DPIA approval, DPA signature, stage sign-off (humans named in manual gates) |

## quality (`forjate:quality`)

| | |
|---|---|
| **Inputs** | brief, plan (`exit_criteria`), business record (`kpi_metric`, `kpi_target`, `approver`), every other record (`gate_to_next`, `verify_assertions`, `eval_strategy`, `untrusted_inputs`), packs (`deny_setting_value` on `judge`, `deny_components` on monitoring, baseline guidelines), `usecase.yaml` when present |
| **Emits** | record mode: `choice: []`; settings `verify_job`, `verify_assertions`, `test_pyramid`, `golden_set`, `judge`, `eval_threshold`, `injection_suite`, `regression_trigger`, `kpi_metric`, `kpi_metric_source`, `observability_signals`, `gate_policy`, `manual_gates_justified`; gates `G-Q-n`. Consolidate mode: `.builder/gates.yaml` with every record's gates verbatim per transition, a `check` on each, the approver per transition and `pack_overrides` |
| **Pushes back when** | a verify Job only checks readiness or skips the exception path or idempotency; a `metric` gate has no source (open question, `caused_by_rule` when a pack removed the stack); an LLM judge is proposed as the only grader; a golden set omits the exceptions or is built on real regulated data before compliance allows it; two records claim one gate id with different texts (kept apart, open question); a manual gate has no justification |
| **Never decides alone** | the gates' texts (copied verbatim from the owners); the monitoring stack (devops); the KPI (business); the seed (data-pipeline) |

## devops (`forjate:devops`)

| | |
|---|---|
| **Inputs** | brief (`budget_per_month_usd`, `residency`), plan (`forjate_tier`, cost), business record (envelope), security (`psa_level`, `secrets_mechanism`, `network_policy`, `deploy_from`), data-store (`backup`, `data_residency`), architecture (`workloads`), compliance records if present, packs (`min_psa_level`, `secrets_mechanism`, `data_residency`, `naming_pattern`, `max_cost_usd_month`, `deny_components`), `docs/lab-to-production.md`, `docs/ci-cd.md`, `tenant-patterns.md` |
| **Emits** | `choice`: `apps/continuous-delivery/argocd`, the stage's secrets component (same as security), `apps/storage/longhorn`, `apps/networking/metallb`, `apps/monitoring/prometheus`, `apps/monitoring/grafana`, `apps/monitoring/otel-collector`, `apps/monitoring/reloader`, `apps/docker-registry`; settings `environment`, `cluster_shape`, `storage_class`, `deploy_method`, `gitops`, `argocd_sync`, `target_revision`, `remote_refs`, `argocd_private_refs`, `environments_distinct`, `image_registry`, `image_tag_policy`, `image_writeback`, `image_signing`, `secrets_mechanism`, `secret_rotation`, `psa_level`, `network_policy`, `observability`, `golden_signals`, `alerting`, `backup`, `restore_rehearsed`, `rollback`, `rollback_rehearsed`, `data_residency`; `estimated_cost_usd_month` per stage; gates `G-OPS-n` (`ci`: ref pinning, stage overlay builds, revision check; `manual` with the operator named: rotation, restore and rollback rehearsals, controller-key backup) |
| **Pushes back when** | ArgoCD, Longhorn or a monitoring stack is asked for at Crawl; a remote ref is a branch past Crawl; private refs have no repo-server prerequisites; testing and production resolve to one directory (`environments_distinct: false` is a finding past Crawl); write-back is `sed` on a string or tags are `latest`; rotation exists only in commit messages; a shared setting differs from the record that owns it (open question naming both, never silent); Velero or another missing component is needed (open question, never an invented path); the cost shape does not fit the envelope (states what the envelope buys; the business expert changes `go_no_go`) |
| **Never decides alone** | PSA, secrets mechanism, network policy (security); backup target and retention (data-store, compliance); the workloads (architecture); the metrics' meaning (quality); the budget (business) |

## ux (`forjate:ux`)

| | |
|---|---|
| **Inputs** | brief (`actors`, `language`, `classification`), plan (`goal`, `out_of_scope`, exit criteria owned by `ux`), business record (`actors`, `as_is_exceptions`, `kpi_metric`), architecture (`workloads`, `api_surface`, `auth_in_front`, `trigger`), ai-engineering (`tools` with `[requires approval token]`, `escalation:` guardrails, the per-turn budget) and security (`auth_in_front`, `identity_provider`, `tool_write_gate`) records if present, packs (`deny_components` on UI and feedback components, `deny_setting_value` on `surface` and `feedback_capture`), catalog (`roles: chat-ui`, `feedback`) |
| **Emits** | `choice`: `apps/ai-models/open-webui`, `apps/surveys/formbricks` only; settings `surface`, `surface_workload`, `channel`, `audiences`, `hitl_checkpoints` (each `[token]` or `[deterministic]`), `escalation_context`, `feedback_capture`, `feedback_prompt`, `latency_budget`, `streaming`, `failure_ux`, `auth_in_front`, `identity_provider`, `ui_language`, `onboarding`; gates `G-UX-n` (`verify-job` for the escalation context, `metric` for feedback rates, `manual` for the walkthrough or shadow period with the signer named) |
| **Pushes back when** | a chat UI or a page is asked for a batch or an operator-only flow (`surface: none`/`cli`, the page is a rejected alternative); an exception path has no surface (names the CSV or the mailbox as the surface and what it lacks: no token, no per-person audit); a human-facing surface has `auth_in_front: none` past Crawl or needs a workload the architecture record lacks (open question naming both records and both values); a survey tool is asked for at Crawl or for a chat user; a write tool requires a token no checkpoint issues (open question to ai-engineering); a pack forbids the only surface that can serve the exception path (surface left unset for the stage, question with `caused_by_rule`) |
| **Never decides alone** | the workloads and the API surface (architecture); which tools need a token (ai-engineering); the auth in front of a surface (architecture and security); the allowed fields a surface may show (ai-engineering and the requester); the KPI (business) |

## Adding an expert

See `how-to-add-an-expert.md`.

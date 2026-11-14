---
title: "Durable workflow / execution engines: open-source landscape for the Forjate agent harness"
date: 2026-10-30
status: research
sources_verified: true
verification_method: "GitHub API (licence SPDX id, stars, latest release, archived flag) queried 2026-10-30; LICENSE files fetched raw where the SPDX id was NOASSERTION; foundation status from cncf.io / project blogs"
---

# Durable workflow / execution engines: OSS landscape

Scope: alternative execution layers for a Forjate agent harness (deterministic workflows that run agent tasks). Temporal is the baseline and is covered in depth in `01-temporal-as-agent-harness.md`. Hard filter: Apache-2.0 / MIT / BSD. Flagged and excluded: AGPL, SSPL, BUSL, Camunda License, "fair-code". Preference: foundation governance, Go, Kubernetes-native, UI separable from execution, declarative DSL and/or code, AI builder emits the graph first.

All stars, versions and dates were read from the GitHub API on **2026-10-30** unless stated otherwise.

## TL;DR

- **Only four engines clear every filter at once (permissive licence + foundation governance + Go + K8s-native):** Argo Workflows (CNCF graduated), Dapr Workflow (CNCF graduated), Tekton (CNCF incubating since 2026-03-13) and Cadence (CNCF sandbox since 2025-05-22). Temporal, Conductor, Kestra, Hatchet, DBOS and Elsa are permissive but single-vendor or single-maintainer.
- **Best DSL-first candidates:** Conductor OSS (JSON DSL, `HUMAN`/`WAIT` tasks, native LLM/MCP tasks, Apache-2.0, 32.4k stars, v3.33.0 on 2026-10-26) and Kestra (YAML, Apache-2.0 core incl. AI Copilot and MCP server, Helm chart in-repo, v2.0.7 on 2026-10-20). Both are vendor-governed (Orkes, Kestra Technologies).
- **Best code-first durable-execution candidates:** Dapr Workflow + Dapr Agents (CNCF, Apache-2.0, Go runtime, event-sourced replay, Dapr Agents v1.0 GA announced by CNCF 2026-03-23) and Temporal (MIT, already in Forjate). DBOS and Hatchet are lighter Postgres-only options (MIT) but vendor-governed and UI-less (DBOS) or 0.x (Hatchet v0.114.2).
- **Exclude on licence:** Inngest (SSPL + delayed Apache after 3 years), Restate (BSL 1.1, 4-year change date), Windmill (AGPLv3 + proprietary EE), LittleHorse (AGPL-3.0 server), Camunda 8 / Zeebe (Camunda License 1.0 since 8.6, 2024-10-08). Keptn is CNCF-archived (2025-09-08).
- **Recommended shortlist for Forjate:** (1) Temporal as the durable kernel, (2) Dapr Workflow/Agents as the foundation-governed alternative kernel, (3) Conductor OSS as the DSL-first engine if the "graph-first" requirement dominates, (4) Argo Workflows for pod-per-step K8s jobs already in the GitOps stack. A hybrid "own DSL compiled onto Temporal or Dapr" is the design that satisfies the AI-builder requirement without inheriting a vendor's DSL.

## Comparison matrix

Legend: Gov = governance; Lic = licence (verified 2026-10-30); Def = definition style; Dur = durability model; HITL = human-in-the-loop; K8s = deployment story; UI sep = UI separable from execution; Agent = agent/LLM features.

| Engine | Gov | Lic | Lang | Def | Dur | HITL | K8s | UI sep | Agent | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Temporal | Vendor (Temporal Technologies) | MIT (server + UI) | Go | Code (Go/Java/Py/TS/.NET/PHP/Ruby) | Event-sourced history + replay | Signals, updates, timers | Helm (official), no CRDs | Yes (ui-server separate) | OpenAI Agents SDK GA 2026-03-23, Nexus | Baseline; strongest durability, already in Forjate |
| Conductor OSS | Community org `conductor-oss`, steered by Orkes | Apache-2.0 | Java | JSON DSL (+ SDK builders) | DB-backed state machine, queue-driven | `HUMAN`, `WAIT` tasks, signals | Docker Compose official; no Helm chart in repo (community charts) | Yes (`ui`, `ui-next` separate containers) | `ai` module: LLM tasks, vector DBs, MCP, A2A | Top DSL-first candidate; JVM, vendor-steered |
| Argo Workflows | CNCF graduated (2022-12-06) | Apache-2.0 | Go | YAML CRDs (DAG/steps) | K8s CR status in etcd; pod per step; archive to Postgres/MySQL | `suspend` template + resume | Native (CRDs, controller, Helm) | Yes (controller runs standalone; argo-server optional) | None native; KFP uses it | Best for pod-per-step jobs; not a long-running agent loop |
| Tekton Pipelines | CNCF incubating (2026-03-13; ex-CDF graduated) | Apache-2.0 | Go | YAML CRDs (Pipeline/Task) | CR status; pod per TaskRun | None native | Native (CRDs, operator) | Yes (Dashboard separate) | None | CI/CD only; out for agent harness |
| Dapr Workflow | CNCF graduated (2024-11-12) | Apache-2.0 | Go runtime; SDKs Py/.NET/Java/JS/Go | Code (orchestrator functions) | Event-sourced history + replay (durabletask-go) via actors; any state store | `wait_for_external_event`, `raise_event`, durable timers | Native (Helm, operator, sidecar/CRDs) | No bundled UI (Diagrid Conductor is commercial) | Dapr Agents v1.1.0 (2026-10-27): DurableAgent, MCP, orchestrators | Top foundation-governed code-first option |
| Apache Airflow 3 | ASF | Apache-2.0 | Python | Python DAGs (Task SDK; Go/Java SDK since 3.3) | DB-backed task state; not durable-execution | HITL operators (3.1, 2025-09-25) | Official Helm chart | Yes (API server/UI separate from scheduler) | HITL, inference DAGs, event-driven assets | Scheduler for batch; weak as agent runtime |
| Kestra | Vendor (Kestra Technologies) | Apache-2.0 core; EE proprietary | Java | YAML DSL | DB-backed (JDBC) or Kafka-backed state machine | `Pause` task (OSS); Cases (EE) | Helm charts in repo | Partly (webserver is a separate server role; same binary) | AI Copilot (OSS), MCP server/trigger, AI Agent task | Strong DSL-first; JVM, vendor, EE gates RBAC/SSO/secrets |
| Elsa Workflows | Individual/community (Elsa Workflows org) | MIT | C# (.NET) | JSON, C# fluent, designer | DB-backed bookmarks (EF Core/MongoDB) | Bookmarks, user tasks, signals | Docs + Helm guidance; DistributedWorkflowRuntime | Yes (Elsa Studio is a separate Blazor app) | `Elsa.Agents` (Semantic Kernel / MS Agent Framework) | Good designer; .NET and no foundation; niche fit |
| Flowable | Vendor (Flowable AG) | Apache-2.0 (engine) | Java | BPMN/CMMN/DMN XML | DB-backed state machine (wait states) | User tasks, messages, signals | Docker; embed in Spring Boot | UI apps removed in v7; Design is a commercial/cloud tool | None | Mature BPMN; UI gap and JVM |
| Open Workflow Spec (ex Serverless Workflow) + runtimes | CNCF sandbox (2020-07-14) | Apache-2.0 | Spec; Go SDK v4.0.0; runtimes Java (SonataFlow), C# (Synapse) | YAML/JSON DSL v1.0.1 (2026-07-31) | Runtime-dependent | `listen`/events | SonataFlow operator (Apache KIE, incubating); Synapse operator | Synapse has dashboard; SonataFlow uses Data Index/Mgmt console | None | Portable DSL, immature runtimes; viable as a DSL *standard*, not an engine |
| DBOS Transact | Vendor (DBOS Inc) | MIT | Py/TS/Go/Java libs | Code (decorators) | Step checkpointing in Postgres | `send`/`recv`, `set_event`/`get_event` | Library in your pods + Postgres; no control plane | No OSS UI (Conductor/Console commercial) | Agent examples only | Minimal, elegant; no UI, vendor |
| Hatchet | Vendor (Hatchet Technologies) | MIT | Go | Code (DAGs + durable tasks) | Event-log checkpointing in Postgres | Durable `wait_for` events, sleep | Helm charts (`hatchet-stack`, `hatchet-ha`, MIT) | Yes (frontend separate Deployment) | Agentic HITL patterns in docs | Promising; still 0.x (v0.114.2) |
| Trigger.dev | Vendor | Apache-2.0 (verified) | TypeScript | Code (TS tasks) | Checkpoint/restore of runs | Waitpoint tokens | Helm chart (`hosting/k8s/helm`); heavy stack (PG, Redis, ClickHouse, S3, registry) | Webapp = API + dashboard (not separable) | AI-agent oriented docs | TS-only, heavy; out for a Go harness |
| Cadence | CNCF sandbox (2025-05-22) | Apache-2.0 (LICENSE as of 2026-10-30) | Go | Code (Go/Java) | Event-sourced history + replay | Signals, timers | Helm (community/Instaclustr) | Yes (cadence-web, Apache-2.0) | None | Temporal's ancestor; smaller ecosystem |
| Flyte 2 | LF AI & Data | Apache-2.0 | Go backend, Py SDK | Pure Python (v2) | Durable task checkpoints; pod per task | Limited (approval via Union features) | Native (Helm, CRDs) | Yes (console separate) | "Durable AI runtime", agent patterns | Data/ML focus; Union-dominated |
| Prefect 3 | Vendor (Prefect) | Apache-2.0 (verified; no Community License in repo) | Python | Python flows | DB-backed state | Pause/resume, inputs | Helm chart | Yes (server+UI vs workers) | Minor | Python batch orchestration |
| Dagster | Vendor (Dagster Labs) | Apache-2.0 | Python | Python assets | DB-backed run state | Limited | Helm chart | Yes (webserver separate) | Minor | Data assets, not agents |
| Apache DolphinScheduler | ASF | Apache-2.0 | Java | Visual DAG / JSON | DB-backed | Manual approval via UI | Helm chart | Yes (api-server separate) | None | Data scheduling; low agent fit |
| Camunda 8 / Zeebe | Vendor | Camunda License 1.0 (since 8.6, 2024-10-08) — **not OSS** | Java | BPMN | Event-sourced log | User tasks | Helm | Yes | None | Excluded on licence |
| Inngest | Vendor | SSPL 1.0 + Apache-2.0 grant after 3 years — **excluded** | Go | Code (step functions) | Step checkpointing | `waitForEvent` | Docker/Helm | Dev server UI | AgentKit | Excluded on licence |
| Restate | Vendor | BSL 1.1 (4-year change) — **excluded** | Rust | Code | Journaled replay | Awakeables | Helm/operator | Yes | Agent docs | Excluded on licence |
| Windmill | Vendor | AGPLv3 + proprietary EE — **excluded** | Rust/TS | Scripts + flow JSON/YAML | DB-backed | Approval steps | Helm | Bundled | AI flow builder | Excluded on licence |
| LittleHorse | Vendor | AGPL-3.0 server/dashboard; Apache SDKs — **excluded** | Java | Code (WfSpec) | Kafka-backed | User tasks, events | Helm | Yes | None | Excluded on licence |
| Kubeflow Pipelines | CNCF graduated (Kubeflow, 2026-08-17) | Apache-2.0 | Python/Go | Python DSL compiled to IR, Argo backend | Argo | None | Native | Yes | ML pipelines | ML-only wrapper on Argo |
| Argo Events | CNCF graduated (Argo) | Apache-2.0 | Go | YAML CRDs (EventSource/Sensor) | n/a (trigger layer) | n/a | Native | n/a | None | Trigger layer for Argo Workflows |
| Numaflow | Vendor (Intuit); no CNCF mention in README | Apache-2.0 | Rust/Go | YAML Pipeline CRD | Stream processing, not workflow | n/a | Native | Yes | "AI agents on streams" marketing | Wrong category (streaming) |
| Keptn Lifecycle Toolkit | CNCF **archived** 2025-09-08 | Apache-2.0 | Go | CRDs | n/a | n/a | Native | n/a | None | Dead; out |

## Per-engine notes

### Temporal (baseline)
Temporal Technologies owns the project; server and UI are MIT (`temporalio/temporal`, `temporalio/ui`). Server v1.32.1 (2026-10-08), UI v2.57.0 (2026-10-21), 24.1k stars. Go. Workflows are code; durability is event-sourced history replayed by deterministic workers. Signals/updates/queries give HITL. Official Helm chart, no CRDs; UI server is a separate deployment that talks to the frontend gRPC. Agent features: OpenAI Agents SDK integration GA 2026-03-23, Nexus cross-namespace operations, AI cookbook. Verdict: the durability gold standard, already shipped in Forjate; the question is only whether a DSL layer sits on top.

### Netflix Conductor / Conductor OSS
`Netflix/conductor` was archived on 2023-12-22; `conductor-oss/conductor` (Apache-2.0, Java, 32.4k stars, v3.33.0 on 2026-10-26) is the continuation, run by Orkes with community SDKs (Go, Python, TS, C#, Rust, Clojure, Ruby). Workflows are JSON documents (tasks, `SWITCH`, `FORK_JOIN`, `DO_WHILE`, `SUB_WORKFLOW`, `DYNAMIC_FORK`); workers poll task queues over HTTP/gRPC, so execution is fully decoupled from the server and UI. Durability is a persisted state machine (Postgres/MySQL/Redis/Cassandra + Elasticsearch/OpenSearch indexing), not replay; workers are stateless. HITL: `HUMAN` and `WAIT` system tasks, resumed via API signal. The repo now ships an `ai` module (LLM chat/complete/embeddings, vector DB config, MCP, agent-to-agent) and both `ui` and `ui-next` frontends as separate containers. Kubernetes: the repo root has no Helm chart (verified 2026-10-30), only Docker Compose; community charts exist. Verdict: the most complete DSL-first engine that is permissively licensed; costs are the JVM footprint and single-vendor steering.

### Argo Workflows
CNCF graduated with the Argo project on 2022-12-06. Apache-2.0, Go, 17.1k stars, v4.0.0 on 2026-02-04, v4.1.6 on 2026-10-22. Workflows are YAML CRDs (`Workflow`, `WorkflowTemplate`, `CronWorkflow`); each step is a pod. Durability is the CR status in etcd plus optional workflow archive to Postgres/MySQL; there is no replay and no long-lived in-process state. HITL: `suspend` templates resumed via `argo resume` or the API. The controller runs standalone; `argo-server` (API + UI) is a separate optional Deployment. No agent features. Verdict: ideal for "run this tool as a K8s job" steps and already GitOps-friendly, but a poor fit for a chatty agent loop (pod per step, no signals richer than suspend/resume).

### Tekton
Apache-2.0, Go, 9.1k stars, v1.18.0 on 2026-10-29. Moved from CD Foundation (graduated) to CNCF incubating on 2026-03-13 (announced 2026-03-24). YAML `Task`/`Pipeline` CRDs, pod per TaskRun, Dashboard separate. No native HITL, no agent features. Verdict: CI/CD engine; out of scope for the harness, but a legitimate Forjate component for builds.

### Dapr Workflow and Dapr Agents
Dapr graduated CNCF on 2024-11-12. Apache-2.0, Go runtime, 26.2k stars, v1.19.0 on 2026-10-22 ("faster workflows, jobs and reminders"). Dapr Workflow is code-first (Python, .NET, Java, JS, Go SDKs) on `durabletask-go` (v0.15.1, 2026-10-19): event-sourced history, replay, durable timers, child workflows, `wait_for_external_event`/`raise_event` for approvals; state lives in any Dapr state store (Postgres, Redis, etc.) via actors. Kubernetes-native (Helm, operator, sidecar injection, CRDs for components). No bundled workflow UI: observability comes from tracing/metrics or Diagrid's commercial Conductor. Dapr Agents (Apache-2.0, Python, 768 stars) reached v1.0 GA on 2026-03-23 (CNCF announcement) and is at v1.1.0 (2026-10-27): `DurableAgent` runs on Dapr Workflow, MCP tool discovery from the sidecar, LLM/round-robin/random orchestrators, pub/sub multi-agent messaging. Verdict: the only foundation-governed stack that combines durable execution with an agent framework; the cost is the sidecar model and a Python-first agent SDK.

### Apache Airflow 3
ASF, Apache-2.0, Python, 47.3k stars, 3.3.2 on 2026-09-17. 3.0 (2025-04-22) split the Task SDK from the scheduler; 3.1 (2025-09-25) added Human-in-the-Loop operators and synchronous "inference" DAGs; 3.2 (2026-04-07) asset partitioning and multi-team; 3.3 (2026-07-06) Java and Go Task SDKs, task/asset state store, pluggable retries. DAGs are Python; state is DB-backed task instances, not durable execution of in-function code. Official Helm chart; API server/UI are separate from scheduler and workers. Verdict: a scheduler, not a durable runtime; useful if the harness needs cron/batch, not as the agent kernel.

### Kestra
Kestra Technologies (vendor). Repo licence Apache-2.0 with proprietary Enterprise Edition features (SSO, RBAC, multi-tenancy, secrets-manager integrations, Cases, Worker Groups 2.0, Policies, Promote). Java, 30.1k stars, v2.0.0 on 2026-09-07, v2.0.7 on 2026-10-20. Flows are YAML; 2.0 introduced a gRPC controller separating control plane from data plane, "workers anywhere" task runners, MCP server and MCP tool trigger, AI Agent task, and the AI Copilot (Ask/Edit/Plan modes) in the open-source edition. Durability is a JDBC- or Kafka-backed state machine with retries; HITL via the `Pause` task (OSS) and Cases (EE). Helm charts live in `charts/` in the repo; the UI is served by the `webserver` server role, which can be scaled separately from executor/worker/scheduler but is the same artifact. Verdict: the best YAML-first developer experience and an AI copilot that already emits the DSL; watch the EE boundary (RBAC and secrets backends matter for a multi-tenant factory).

### Elsa Workflows
MIT, C#/.NET, 7.9k stars, 3.9.0 on 2026-10-04; maintained by a small core team (no foundation). Definitions in JSON, C# fluent API or the designer; execution model is bookmark-based (blocking activities persist a bookmark and the instance is resumed by a stimulus), persisted via EF Core (SQL Server, Postgres, MySQL, SQLite) or MongoDB. `DistributedWorkflowRuntime` plus distributed locks/cache and clustered Quartz are required for multiple replicas; docs include Kubernetes and Helm guidance. Elsa Studio (separate repo, MIT, 303 stars, 3.9.0 same day) is a Blazor app talking to Elsa Server's REST API, so UI and execution are cleanly separated. `Elsa.Agents` adds agent activities via Semantic Kernel / Microsoft Agent Framework. Verdict: exactly the "designer produces JSON, code wired later" model Sebas described, but .NET-only, individual governance and a small ecosystem.

### Flowable
Flowable AG (vendor), engine Apache-2.0, Java, 9.6k stars, 8.0.0 on 2026-02-27. BPMN 2.0, CMMN and DMN XML executed by a DB-backed engine with wait states, user tasks, timers, messages and signals; typically embedded in Spring Boot. Version 7 removed the open-source UI apps; modelling is done in Flowable Design (free cloud edition, commercial platform). Docker images exist; no official operator. Verdict: the most standards-complete DSL (BPMN) under a permissive licence, but UI/designer are now commercial and it is JVM-embedded.

### Open Workflow Specification (ex Serverless Workflow) and runtimes
CNCF sandbox since 2020-07-14, Apache-2.0, spec v1.0.1 on 2026-07-31 (946 stars). The project renamed itself "Open Workflow Specification" (the DSL spans beyond serverless). SDKs: Go v4.0.0 (2026-07-14), Java, TypeScript, Python, .NET, PHP, Rust. Runtimes: **Synapse** (C#, Apache-2.0, 314 stars, operator + runner + correlator on K8s) whose last pre-release is v1.0.0-alpha5.20 on 2025-08-26; **SonataFlow** (Apache KIE, incubating, Java/Quarkus, 10.2.0 on 2026-04-28; the standalone operator repo was archived 2024-11 and moved into `incubator-kie-tools/packages/sonataflow-operator`; `kogito-runtimes` archived 2026-07); plus Quarkus Flow and Lemline. Verdict: a vendor-neutral, foundation-governed **DSL** that an AI builder can target, but no production-grade Go runtime; use the spec, not the runtimes.

### DBOS Transact
DBOS Inc (vendor), MIT. Python 3.4.0, TypeScript v5.4 and Go v1.8.0 all released 2026-10-28; Java SDK also MIT. A library: decorated workflows and steps checkpoint inputs and outputs to Postgres (one write per step), recovery resumes from the last completed step; no server component. HITL via `send`/`recv` messages and `set_event`/`get_event`; durable sleep and queues included. No open-source UI; DBOS Conductor/Console are commercial. Verdict: smallest footprint and good Go support, but UI-less and vendor-only; fits as an embedded durability primitive, not as the harness control plane.

### Hatchet
Hatchet Technologies (vendor, YC), MIT, Go, 8.2k stars, v0.114.2 on 2026-10-26 (still 0.x). Code-first DAGs plus durable tasks that checkpoint to a Postgres event log; durable `wait_for` on events and sleep enable agentic HITL; dynamic DAGs at runtime. Official Helm charts (`hatchet-stack`, `hatchet-ha`, MIT) deploy engine (gRPC), API, frontend, Postgres and RabbitMQ (chart still lists RabbitMQ; verify whether current engine needs it). Frontend is a separate Deployment. Verdict: closest Go-native "Temporal-lite" with a UI, but pre-1.0 and single-vendor.

### Trigger.dev
Apache-2.0 (LICENSE file verified, no EE carve-outs), TypeScript, 16.7k stars, v4.8.3 on 2026-10-30. Tasks are TS code; runs are checkpointed and resumed; waitpoint tokens give durable HITL. Helm chart in `hosting/k8s/helm` deploys webapp (API + dashboard, one component), supervisor, Postgres, Redis, ClickHouse, object storage, registry and a realtime stream backend; the docs state the chart alone will not produce a hardened deployment. Verdict: licence-clean but TS-only and operationally heavy; not a fit for a Go harness.

### Cadence
Uber donated Cadence to CNCF sandbox on 2025-05-22; LICENSE is Apache-2.0 as of 2026-10-30 (the brief said MIT; the current repo says Apache-2.0, flagging the discrepancy). Go, 9.5k stars, v1.4.2 on 2026-10-02; `cadence-web` Apache-2.0. Same replay model as Temporal (common ancestor). Helm charts are community/Instaclustr. Verdict: foundation-governed Temporal sibling with a smaller SDK set and ecosystem; only worth it if foundation governance outranks Temporal's maturity.

### Flyte, Prefect, Dagster, DolphinScheduler (data-orchestration angle)
- **Flyte**: LF AI & Data, Apache-2.0, Go backend, 7.8k stars; Flyte 2 GA (v2.0.0 on 2025-12-22, v2.0.53 on 2026-10-27) replaces the DSL with pure Python and markets itself as a "durable AI runtime". Union.ai dominates development. Pod-per-task; fine for ML jobs, heavy for agent loops.
- **Prefect 3**: Apache-2.0 for the whole repo (LICENSE verified; the old "Prefect Community License" for `/server` no longer exists in the repo), Python, 24.1k stars, 3.9.1 on 2026-10-30. Server + UI separate from workers; pause/resume with inputs. Python batch orchestration.
- **Dagster**: Apache-2.0, Python, 16.4k stars, 1.13.28 on 2026-10-30; asset-centric; Dagster+ commercial. Not an agent runtime.
- **Apache DolphinScheduler**: ASF, Apache-2.0, Java, 14.5k stars, 3.4.3 on 2026-09-06; low-code visual DAGs, Helm chart, api-server separate. Data scheduling, low agent fit.

### Excluded on licence
- **Camunda 8 / Zeebe**: Camunda License 1.0 for Zeebe, Operate, Tasklist since 8.6 (2024-10-08); production use requires a licence. Only clients/protocol are Apache-2.0. 8.10.7 on 2026-10-26. Out.
- **Inngest**: SSPL 1.0 with an irrevocable Apache-2.0 grant three years after each release ("delayed open source"); Go, v1.49.0 on 2026-10-23. Out (SSPL today).
- **Restate**: Business Source License 1.1, change date four years after release, additional use grant forbids offering Restate APIs as a managed service to third parties; Rust, v1.8.1 on 2026-10-21. Out.
- **Windmill**: AGPLv3 community build plus proprietary enterprise features (Apache-2.0 only for API clients); v1.855.1 on 2026-10-30. Out.
- **LittleHorse**: server and dashboard AGPL-3.0, SDKs Apache-2.0; v1.3.1 on 2026-10-29. Out.
- **Keptn Lifecycle Toolkit**: Apache-2.0 but CNCF archived 2025-09-08, last release 2025-03-19. Out.

### Other Go/K8s/foundation engines checked
- **Kubeflow Pipelines**: Kubeflow graduated CNCF on 2026-08-17; KFP 2.18.0 (2026-10-28) compiles Python to an IR executed by Argo Workflows. ML-pipeline wrapper, nothing to add for agents beyond Argo.
- **Argo Events**: Apache-2.0, v1.9.11 (2026-07-13); EventSource/Sensor CRDs that trigger Argo Workflows or anything else. Useful as the trigger layer if Argo is adopted.
- **Numaflow**: Intuit, Apache-2.0, v1.9.0 (2026-10-29); streaming pipelines, not workflows; README does not claim CNCF status (not verified as a CNCF project).
- **Knative Eventing**: CNCF graduated; CloudEvents brokers/triggers, not a workflow engine; relevant only as an event bus for a harness.

## Shortlist for Forjate (max 4)

1. **Temporal (keep as kernel).** MIT, Go, already a Forjate component, best-in-class replay durability, signals/updates for HITL, separate UI, official Helm, and a GA agent integration. Weakness: vendor governance and no DSL. Mitigation: the harness owns a DSL and compiles it to a generic Temporal workflow interpreter.
2. **Dapr Workflow + Dapr Agents (foundation-governed alternative kernel).** CNCF graduated, Apache-2.0, Go runtime, same event-sourced model, K8s-native, and the only stack whose agent framework is also foundation-governed. Weakness: no OSS workflow UI, sidecar operational model, Python-first agents. Fits Forjate's "foundation over vendor" rule better than Temporal; decide by whether a UI is mandatory on day one.
3. **Conductor OSS (DSL-first engine).** Apache-2.0, JSON DSL that an AI builder can emit directly and validate against the schema, `HUMAN`/`WAIT` tasks, native LLM/MCP tasks, UI as a separate container, polyglot workers (Go SDK). Weakness: JVM server, no official Helm chart, Orkes steering. Pick if "graph first, wiring later" must be native rather than built.
4. **Argo Workflows (K8s job executor).** Not a kernel for agent loops but the right engine for steps that are containers (builds, scans, data jobs); it is already GitOps-native and Forjate-shaped. Pair with Temporal/Dapr for the long-running control loop.

Honourable mentions: Kestra (best YAML UX and OSS AI Copilot; vendor + EE gating of RBAC/secrets), Hatchet (Go, MIT, Helm, UI; pre-1.0), Elsa (ideal designer model; .NET), Open Workflow Spec (adopt the DSL schema, not the runtimes).

## DSL-first vs code-first for an AI builder that generates the graph first

**DSL-first engines (Conductor, Kestra, Elsa, Open Workflow Spec, Argo, Flowable).** The workflow is data: a JSON/YAML/XML document the engine validates, stores, versions and renders. That is precisely what an LLM-assisted builder wants to produce: it can emit the graph, the schema catches structural errors before anything runs, the UI shows the graph immediately, and the "implementation wiring" is a separate step of registering workers for named task types (Conductor), plugins (Kestra), activities (Elsa) or container images (Argo). Trade-offs: control flow is limited to what the DSL offers (loops, branches, forks), dynamic graphs are awkward, and durability is a state machine over persisted task statuses rather than replayed code, so each engine has its own semantics for retries, timeouts and partial failure. Conductor's `DYNAMIC_FORK` and `SUB_WORKFLOW` and Kestra's `ForEach`/`Subflow` cover most agent patterns; genuinely open-ended ReAct loops become `DO_WHILE` around an LLM task with a `SWITCH` on the model's decision.

**Code-first durable execution (Temporal, Dapr Workflow, DBOS, Hatchet, Cadence).** The workflow is a deterministic function; the graph exists only implicitly in execution history. Strengths: arbitrary control flow, typed data, unit-testable workflows, the strongest durability semantics (replay or step checkpointing), and signals that make HITL trivial. Weakness for the stated requirement: an AI builder cannot "produce the graph first" because there is no graph artifact until code exists; generating workflow code directly is possible but hands the model the determinism constraints (no non-deterministic calls inside the workflow), and the UI can only render history, not intent.

**Recommended synthesis.** Keep the graph as data and the engine as code: define a small Forjate workflow DSL (or adopt the Open Workflow Spec v1.0.1 schema, CNCF-governed and Apache-2.0, so the format is not Forjate-specific), let the AI builder emit and validate that document, and execute it with a *generic interpreter workflow* on Temporal or Dapr Workflow that walks the graph node by node, mapping node types to activities and `wait` nodes to signals. This yields the DSL-first authoring model, the code-first durability model, a UI that can show the authored graph alongside engine history, and no dependence on a vendor's DSL. Conductor is the fallback if building that interpreter is judged not worth it, since it already is that interpreter.

## Verification notes and open items

- All licences were checked via GitHub's SPDX detection and, where it returned NOASSERTION (Inngest, Restate, Windmill), by reading the raw LICENSE file on 2026-10-30.
- Not verified: an official Helm chart for Conductor OSS (repo root has none; community charts exist); whether Hatchet's current engine still requires RabbitMQ (chart lists it); Numaflow's CNCF status (README silent); Cadence's licence history (brief said MIT, repo says Apache-2.0 today).
- Synapse's latest tag is an alpha from 2025-08-26 although commits continued into 2026-10; treat as pre-production.
- Kestra EE boundary was read from docs on 2026-10-30 and may move between minor versions.

## Sources

- Temporal: https://github.com/temporalio/temporal, https://github.com/temporalio/ui, https://temporal.io/blog/announcing-openai-agents-sdk-partnership, https://docs.temporal.io/develop/python/integrations/openai-agents
- Conductor OSS: https://github.com/conductor-oss/conductor, https://github.com/Netflix/conductor (archived 2023-12-22), https://docs.conductor-oss.org/documentation/configuration/workflowdef/systemtasks/index.html
- Argo Workflows: https://github.com/argoproj/argo-workflows/releases, https://argo-workflows.readthedocs.io/en/latest/architecture/, https://argo-workflows.readthedocs.io/en/latest/walk-through/suspending/, https://cncf.io/announcements/2022/12/06/the-cloud-native-computing-foundation-announces-argo-has-graduated
- Tekton: https://github.com/tektoncd/pipeline/releases, https://www.cncf.io/blog/2026/03/24/tekton-becomes-a-cncf-incubating-project/, https://tekton.dev/blog/2026/03/25/tekton-joins-the-cncf-as-an-incubating-project/
- Dapr: https://github.com/dapr/dapr/releases, https://github.com/dapr/durabletask-go, https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-features-concepts/, https://cncf.io/announcements/2024/11/12/cloud-native-computing-foundation-announces-dapr-graduation
- Dapr Agents: https://github.com/dapr/dapr-agents, https://docs.dapr.io/developing-ai/dapr-agents/dapr-agents-core-concepts/, https://www.cncf.io/announcements/2026/03/23/general-availability-of-dapr-agents-delivers-production-reliability-for-enterprise-ai/
- Airflow: https://github.com/apache/airflow/releases, https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html
- Kestra: https://github.com/kestra-io/kestra, https://kestra.io/docs/whats-new-2-0, https://kestra.io/docs/enterprise, https://kestra.io/blogs/release-2-0
- Elsa: https://github.com/elsa-workflows/elsa-core, https://github.com/elsa-workflows/elsa-studio, https://docs.elsaworkflows.io/hosting/distributed-hosting, https://docs.elsaworkflows.io/guides/ai-agents
- Flowable: https://github.com/flowable/flowable-engine, https://documentation.flowable.com/latest/admin/release-notes/2026.1.0-release
- Open Workflow Spec / Serverless Workflow: https://github.com/serverlessworkflow/specification, https://github.com/serverlessworkflow/sdk-go, https://github.com/serverlessworkflow/synapse/releases, https://www.cncf.io/projects/open-workflow-specification/, https://kie.apache.org/docs/10.0.x/sonataflow/serverlessworkflow/latest/cloud/operator/install-serverless-operator.html, https://github.com/apache/incubator-kie-kogito-runtimes (archived), https://github.com/apache/incubator-kie-tools
- DBOS: https://github.com/dbos-inc/dbos-transact-py, https://github.com/dbos-inc/dbos-transact-ts, https://github.com/dbos-inc/dbos-transact-golang, https://docs.dbos.dev/architecture, https://docs.dbos.dev/python/tutorials/workflow-communication
- Hatchet: https://github.com/hatchet-dev/hatchet, https://github.com/hatchet-dev/hatchet-charts, https://docs.hatchet.run/home/durable-execution, https://docs.hatchet.run/self-hosting/kubernetes-quickstart
- Trigger.dev: https://github.com/triggerdotdev/trigger.dev, https://raw.githubusercontent.com/triggerdotdev/trigger.dev/main/LICENSE, https://trigger.dev/docs/self-hosting/kubernetes, https://trigger.dev/docs/wait-for-token
- Inngest: https://github.com/inngest/inngest, https://raw.githubusercontent.com/inngest/inngest/main/LICENSE.md
- Restate: https://github.com/restatedev/restate, https://raw.githubusercontent.com/restatedev/restate/main/LICENSE
- Windmill: https://github.com/windmill-labs/windmill (LICENSE header: Apache-2.0 / AGPLv3 / proprietary EE)
- LittleHorse: https://github.com/littlehorse-enterprises/littlehorse
- Cadence: https://github.com/cadence-workflow/cadence, https://github.com/cadence-workflow/cadence-web, https://www.uber.com/en-UG/blog/cadence-workflow-joins-the-cloud-native-computing-foundation/, https://cadenceworkflow.io/blog/2025/11/12/help-cadence-reach-cncf-incubation
- Flyte: https://github.com/flyteorg/flyte/releases, https://flyte.org/platform/flyte-2, https://web.union.ai/blog-post/flyte-2-is-generally-available-the-durable-open-source-ai-runtime
- Prefect: https://github.com/PrefectHQ/prefect, https://raw.githubusercontent.com/PrefectHQ/prefect/main/LICENSE
- Dagster: https://github.com/dagster-io/dagster
- DolphinScheduler: https://github.com/apache/dolphinscheduler/releases
- Camunda: https://github.com/camunda/camunda, https://camunda.com/blog/2024/10/camunda-licensing-what-you-need-to-know/, https://docs.camunda.io/docs/next/reference/announcements
- Kubeflow: https://github.com/kubeflow/pipelines, https://www.cncf.io/announcements/2026/08/17/cncf-announces-kubeflows-graduation/
- Argo Events: https://github.com/argoproj/argo-events
- Numaflow: https://github.com/numaproj/numaflow
- Keptn: https://github.com/keptn/lifecycle-toolkit, https://castrojo.github.io/jorgepilot/reports/cncf/cncf-archived-projects-report

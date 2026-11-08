---
title: "Open Workflow Specification + Zigflow as the spine that joins the harness"
date: 2026-11-05
status: research
sources_verified: true
verification_method: "Shallow clone of zigflow/zigflow (10a03ed, 2026-10-26; docs/docs/**, examples/**, pkg/zigflow/{tasks,activities,extensions}, pkg/graph, charts/); GitHub API for licence, stars, releases, contributors; zigflow/schema and zigflow/catalog repos listed."
---

# Open Workflow Specification + Zigflow as the spine

Question from Sebas: can the CNCF Open Workflow Specification (OWS) plus Zigflow, which he has been exploring to build flows on Temporal, be the thing that joins everything in this research? Answer: **yes, that is the spine**, with four well-defined gaps to fill around it. This page is the wiring diagram.

## TL;DR

- **Zigflow is a real OWS-on-Temporal runtime, not a toy.** Apache-2.0, Go 1.27, built on `open-workflow-specification/sdk-go v4`. Implements `do`, `for`, `fork`, `switch`, `try`, `raise`, `set`, `wait` (plus `until`), `listen` (as Temporal **query / signal / update**, with `acceptIf` and timeouts), `run` (container on Docker or **Kubernetes Job**, script js/python, shell, child **workflow**), `call: activity` (any Temporal task queue), `call: http`, `call: grpc`. Validation in three stages, Mermaid export, a read-only **MCP server** with schema, examples and validation, Helm chart, Temporal Worker Controller support, continue-as-new handled for you.
- **What it does not implement:** `call: openapi | asyncapi | mcp | a2a` and spec-style CloudEvents `emit`/`listen`; `listen` is deliberately Temporal-native. The project states "correctness and determinism take priority over strict spec compatibility".
- **The plug point for agents is `call: activity` on an external task queue.** Zigflow's own guidance: business logic never goes into the DSL; it goes into activities in your workers. An `agent-worker` task queue in Go (or Python) hosts the executors for kagent (A2A), AX (gRPC), DSH headless or a Kubernetes Job. The `examples/agentic-workflow` is already a bounded plan / act / observe loop built this way.
- **Governance is the weak point:** one maintainer (Simon Emms, 602 of ~670 commits), org created 2026-03-07, 230 stars, v0.18.0 on 2026-10-23, releases every one to two weeks, pre-1.0. The spec underneath is CNCF Sandbox. Mitigation: small codebase, clean extension seam, and a project small enough that Forjate contributions shape it.
- **Everything else in this research attaches to it without a new concept:** the AI builder emits Zigflow YAML (its MCP server supplies schema and validation), GitHub Actions compiles into it, dsh-superagent's intake model starts and signals these workflows, kagent/AX/DSH become activities, OSC 7501 states become search attributes, Forjate ships it as a component next to `temporal-stack`.

## Governance and licence table

| Item | Value (verified 2026-11-05) |
|---|---|
| Repo | github.com/zigflow/zigflow, org created 2026-03-07, repo 2025-08-01 |
| Licence | Apache-2.0 (also zigflow/schema, zigflow/catalog, charts) |
| Foundation | none; built on CNCF Sandbox Open Workflow Specification via `sdk-go v4` |
| Maintainers | mrsimonemms 602 commits; next contributors 14, 7, 7; dependabot |
| Stars / forks / open issues | 230 / 33 / 30 |
| Releases | v0.18.0 (2026-10-23), v0.17.1 (10-18), v0.17.0 (10-16), v0.16.0 (09-27) |
| Language | Go 1.27; activities callable from any Temporal SDK |
| Distribution | binary (brew cask), Docker image, Helm chart `oci://ghcr.io/zigflow/charts/zigflow`, `zigflow-mcp` chart, starter template |
| Spec coverage | OWS 1.0 task set minus `emit`, `call: openapi/asyncapi/mcp/a2a`; CloudEvents package present but `listen` maps to Temporal messages |

## 1. How Zigflow actually runs

`zigflow run -f workflow.yaml` loads one or more definitions, validates (schema → spec → Zigflow constraints), compiles them into a Temporal workflow implementation, registers workflow types and built-in activities on `document.taskQueue`, and polls. Definitions are **data loaded at worker start**: changing a flow means a new worker rollout (inline values, Secret, or the recommended dedicated image with Worker Controller versioning). There is no per-run upload of a definition; the definition is immutable per deployed worker version, which is the right property for replay safety and the reason the builder's "post to Temporal" is really "publish a worker version".

Determinism is enforced structurally: no code in YAML, all side effects are activities, `with:` is evaluated before scheduling so history records resolved values, `set`/`switch`/`for` are deterministic over `$context`, `fork`/`try` compile to child workflows, `continue-as-new` is automatic.

## 2. What maps onto what

```
                 ┌──────────────────────────────────────────────────────────────┐
  authoring      │ Builder UI (React Flow + copilot)  ──emits──▶ Zigflow YAML   │
                 │   schema + validate + examples via Zigflow MCP server         │
                 │   Mermaid view via pkg/graph (round trip for the LLM)         │
                 │   importers: GitHub Actions YAML, n8n JSON  ──compile──▶ YAML │
                 └──────────────────────────────┬───────────────────────────────┘
                                                │ git (definition repo) → image / Helm values
  intake         ┌──────────────────────────────▼───────────────────────────────┐
  (doc 09)       │ Intake service (Go, Temporal): Source→Trigger→Eval→Mandate    │
                 │   starts workflowType=<use case> with Ticket id; sends signals│
                 └──────────────────────────────┬───────────────────────────────┘
  execution      ┌──────────────────────────────▼───────────────────────────────┐
                 │ Zigflow worker(s)  (forjate component, next to temporal-stack)│
                 │   do / for / fork / switch / try / wait / set                 │
                 │   listen: signal|update (+timeout)  ← HITL gates              │
                 │   run: container → Kubernetes Job     ← build/test/scan steps │
                 │   run: workflow → child use cases                             │
                 │   call: activity taskQueue=agent-worker ← AGENT STEPS         │
                 │   call: http → LiteLLM / any REST;  call: grpc → AX           │
                 └──────────────────────────────┬───────────────────────────────┘
  agent runtime  ┌──────────────────────────────▼───────────────────────────────┐
  (docs 07/08/09)│ agent-worker (Go, Temporal activities, heartbeating):         │
                 │   RunKagentTask (A2A; input-required → returns "blocked")     │
                 │   RunAXTask (gRPC CreateTask/GetTask)                         │
                 │   RunDSHHeadless / RunClaudeCode (Job + journal upload)       │
                 │   PolicyGate / Assess (dsh-superagent Eval, LLM via LiteLLM)  │
                 └──────────────────────────────────────────────────────────────┘
  observability    search attributes: ticket, stage(OSC 7501 state), kind
                   OTel from Zigflow (pkg/telemetry) + activity spans; journals as artifacts
```

| Harness need | Zigflow construct | Notes |
|---|---|---|
| Deterministic graph, retries, timeouts | `do`/`for`/`fork`/`switch`/`try`, `metadata.activityOptions`, `metadata.heartbeat` | native |
| Human gate | top-level `listen` to `signal` or `update` with `metadata.timeout`; `update` with `acceptIf` validates the decision | **signal `listen` must be at the top level of a workflow**: inside `try`/`fork` it compiles to a child workflow the parent's signals do not reach. Design use cases so gates sit at top level, or gate inside a child `run: workflow` that is signalled by id from an activity |
| Agent step | `call: activity` on `agent-worker`, arguments = node binding | heartbeat for long LLM calls; returns typed output validated by the node's schema; a `blocked` result followed by a `listen` implements kagent/A2A `input-required` |
| Container step | `run: container` with worker in `--container-runtime=kubernetes` | one Job per task, stdout as result; runtime chosen per worker, so keep a dedicated worker for container steps |
| Sub-flows and fan-out | `run: workflow` (sync) and `fork` of `run: workflow` (async) | child workflows; parent/child signal visibility caveat above |
| Model call | `call: http` to LiteLLM, or an activity | `call: http` keeps the prompt in history; prefer an activity with External Payload Storage for large prompts |
| Scheduling | Temporal Schedules (`examples/schedule`) | cron-like triggers without a separate scheduler |
| Status for the inbox | `metadata` search attributes (`examples/search-attributes`) + `listen: query` | project to OSC 7501 states and AG-UI |
| Evidence | Temporal history + OTel + journals uploaded by activities to MinIO | Zigflow emits traces; `codec` package for encrypted payloads |

## 3. The four gaps, and the pegamento for each

1. **No `call: mcp` / `call: a2a` in Zigflow (they exist in the spec).** Do not wait for them. An MCP tool call or an A2A task is an activity with a JSON-Schema-described argument block; the `agent-worker` implements `CallMCPTool` and `SendA2AMessage` once, in Go, reused by every flow. If Forjate wants spec fidelity later, the extension mechanism is not the place (it is reserved for Temporal workflow primitives); the right move is contributing `call: mcp` upstream as an activity-backed task, which the maintainer's own rules allow.
2. **HITL only at the top level.** The dsh-superagent stage model needs gates in many places. Two patterns work today: (a) flatten use cases so each human gate is a top-level task between child workflows; (b) run the gated section as a child `run: workflow` and have an `agent-worker` activity signal that child by its deterministic id. Pattern (a) is simpler and reads better in the UI.
3. **Definitions are baked into worker versions.** The builder cannot push a YAML into a running worker. This is correct for determinism, so make it the workflow: builder commits YAML to a definitions repo → CI runs `zigflow validate` → image build (dedicated image) → Helm/Argo rollout with Temporal Worker Controller versioning. The Forjate "intent graph → revision" story becomes a GitOps story, which is the house pattern anyway. For fast iteration in a dev overlay, inline values via Helm are fine.
4. **Bus factor.** One maintainer, pre-1.0, fast release cadence. Mitigations: pin versions in the component, keep a fork-ready vendoring path, and contribute (docs, `call: mcp`, Helm tests). The codebase is small (`pkg/zigflow/tasks` is a few dozen files) and the maintainer publishes design articles explaining each decision; it is a project Forjate can realistically co-maintain if needed.

## 4. Where the other research pieces attach

| Piece | Attaches as |
|---|---|
| GitHub Actions schema ([02](02-github-actions-schema-as-agent-dsl.md)) | importer: `jobs`/`needs` → `do` + `fork`; `steps` → `run: container` or `call: activity`; `uses:` → `act` inside a Job; `x-agent:` → agent activities and `listen` gates |
| Builder ([05](05-ai-assisted-workflow-builders-ui.md)) | emits Zigflow YAML; uses the Zigflow MCP server (`get_schema`, `get_task_docs`, `validate`) as the validate-and-repair loop; renders `pkg/graph` Mermaid |
| Canonical IR ([06](06-portable-workflow-dsl-and-interchange.md)) | the IR **is** OWS 1.0 in Zigflow's dialect; `x-forjate-*` goes under `metadata`, the spec's sanctioned extension point |
| AX ([07](07-google-ax-agent-executor.md)) | `call: grpc` directly against ax-server, or an activity wrapping CreateTask/GetTask with heartbeat |
| kagent ([08](08-kagent.md)) | activity speaking A2A; `input-required` → activity returns `blocked`, flow does `listen: signal approve` with timeout, next activity posts the `tool_approval_response` on the same A2A task |
| dsh-superagent model, OSC 7501 ([09](09-software-factory-dsh-superagent-herdr.md)) | intake service starts `workflowType` per use case and sends signals (`trigger`, `stop`, `policyChanged`); ticket stage kept as a search attribute with the 7501 vocabulary |
| Temporal component ([01](01-temporal-as-agent-harness.md)) | Zigflow becomes `components/apps/workflows/zigflow` (Helm, `valuesInline`), one worker per task queue family (`zigflow`, `zigflow-containers`), plus `agent-worker` as a Forjate-owned Go image |
| Crucible | a use case's `verify` Job can be a Zigflow flow; conversely an agent run can live in a Crucible namespace with TTL |

## 5. What to build (architecture-first)

1. **Forjate component `workflows/zigflow`** rendering the official Helm chart with `valuesInline`, pinned version, two workers (`zigflow` and `zigflow-containers` with `--container-runtime=kubernetes`), RBAC for Jobs, OTel to the cluster collector.
2. **`agent-worker` (Go)**: a Temporal worker exposing `PolicyGate`, `Assess`, `CallMCPTool`, `SendA2AMessage`, `RunJob`, `RunKagentTask`, `RunAXTask`, each with a JSON Schema for arguments and result, heartbeats, and OTel GenAI attributes. This is the only Forjate-owned runtime code in the spine.
3. **Definitions repo + CI**: `zigflow validate`, schema check of `metadata.x-forjate-*`, Mermaid regeneration, dedicated image build, Worker Controller rollout.
4. **Three reference flows**, each an architecture stub: *triage-and-pr* (intake → assess → agent → PR → review gate), *scheduled-audit* (Temporal Schedule → container steps → report), *approval-gated-release* (fork of checks → `listen: update` with `acceptIf` → `run: container`).
5. **Builder spike** against the Zigflow MCP server before writing any UI: prompt → YAML → `validate` → repair, measured on the three flows.

## 6. Risks

- Spec divergence: Zigflow's `listen` is not the spec's CloudEvents `listen`; a flow written for Synapse or SonataFlow will not run unchanged if it uses events. Forjate flows should target Zigflow's dialect and keep `metadata` for portability hints.
- Payload size and history growth with LLM content: use External Payload Storage or the codec package, and keep prompts in activities, not `call: http` bodies.
- The maintainer may change the activity-call contract before 1.0; pin and read the CHANGELOG each bump.
- Not verified here: Worker Controller integration end to end on k3s; the `zigflow-mcp` chart's self-hosting story (the public server is hosted by the project); CloudEvents package usage.

## Sources

- https://github.com/zigflow/zigflow (README, docs/docs/architecture.md, concepts/how-zigflow-runs.md, dsl/tasks/{call,run,listen}.md, guides/extending-the-dsl.md, cli/mcp-server.md, deployment/kubernetes.md, examples/{agentic-workflow,approval-timeout,update,child-workflows,run-task-kubernetes}, pkg/zigflow/{tasks,activities,extensions}, pkg/graph, charts/; clone 10a03ed, 2026-10-26)
- https://zigflow.dev/docs and https://mcp.zigflow.dev
- https://github.com/zigflow/schema, https://github.com/zigflow/catalog, https://github.com/zigflow/starter
- Design articles by the maintainer: "Why Zigflow doesn't generate code" (2026-03-21), "From YAML to Temporal: compiling deterministic workflows" (2026-03-22), "When not to use Zigflow" (2026-03-23)
- https://open-workflow-specification.org and github.com/open-workflow-specification/sdk-go (v4)
- GitHub API, 2026-11-05: licence, stars, created_at, releases, contributors

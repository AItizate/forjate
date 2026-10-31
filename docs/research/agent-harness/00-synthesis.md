---
title: "Agent harness on Forjate: synthesis and decision points"
date: 2026-10-30
status: research
sources_verified: see per-axis documents
---

# Agent harness: synthesis

This page cross-reads the six research documents in this folder and extracts what they agree on, where they disagree, and which decisions remain open. Each claim links back to the document that carries the sources; nothing here was re-verified independently.

## What the six documents agree on

1. **Keep the graph as data and the engine as code.** Every document converges on the same shape: an AI-assisted builder emits and iterates a declarative graph (YAML/JSON, schema-validated), and a *generic interpreter workflow* on a durable engine executes it. DSL-first engines give the authoring model; code-first durable execution gives the durability model; the interpreter joins them ([03](03-durable-workflow-engines-oss-landscape.md), [04](04-agent-frameworks-deterministic-workflows.md), [05](05-ai-assisted-workflow-builders-ui.md), [06](06-portable-workflow-dsl-and-interchange.md)).
2. **No existing OSS product covers the whole requirement.** No builder is at once permissively licensed, decoupled from its runtime, executor-agnostic on export, and shipping a self-hostable AI loop. The mature copilots (n8n, Sim, Kestra, Windmill) are either licence-restricted or vendor-hosted even when self-hosted ([05](05-ai-assisted-workflow-builders-ui.md)).
3. **Durability belongs below the agent framework.** LangGraph, Agent Framework, Mastra and CrewAI only self-checkpoint; official Temporal integrations exist for OpenAI Agents SDK and Pydantic AI, and Dapr Agents runs natively on Dapr Workflows ([04](04-agent-frameworks-deterministic-workflows.md), [01](01-temporal-as-agent-harness.md)).
4. **GitHub Actions is an excellent authoring/import format and a poor runtime model.** The schema cannot express loops, unbounded fan-out, per-step retries, long waits, signals or memory, and every workaround depends on the GitHub control plane. GitHub's own Agentic Workflows (gh-aw) prove the authoring idea and inherit every CI limit ([02](02-github-actions-schema-as-agent-dsl.md), [06](06-portable-workflow-dsl-and-interchange.md)).
5. **The governance filter bites hard.** Of everything surveyed, the only foundation-governed pieces that fit are Argo Workflows, Dapr Workflow/Dapr Agents, Tekton, Cadence (all CNCF), Node-RED (OpenJS, but editor welded to runtime), the A2A protocol (Linux Foundation) and the CNCF Open Workflow Specification. Temporal, Conductor, Kestra, ADK, Agent Framework, LangGraph and every builder are single-vendor ([03](03-durable-workflow-engines-oss-landscape.md), [04](04-agent-frameworks-deterministic-workflows.md)).

## Where the documents disagree

| Topic | Position A | Position B | How to read it |
|-------|-----------|-----------|----------------|
| Canonical definition format | [02](02-github-actions-schema-as-agent-dsl.md): use the GitHub Actions schema as authoring format plus a namespaced `x-agent:` extension | [06](06-portable-workflow-dsl-and-interchange.md), [05](05-ai-assisted-workflow-builders-ui.md): use the CNCF Open Workflow Specification 1.0 as the canonical IR | Not contradictory if there is **one** IR and GitHub Actions is an **import/export adapter**. The open question is which format the builder edits natively (see decision 2). |
| Engine kernel | [01](01-temporal-as-agent-harness.md), [04](04-agent-frameworks-deterministic-workflows.md): keep Temporal (already in Forjate, MIT, richest agent integrations) | [03](03-durable-workflow-engines-oss-landscape.md): Dapr Workflow + Dapr Agents fits the "foundation over vendor" rule better | Same execution model (event-sourced replay). Temporal wins on tooling and on what Forjate already ships; Dapr wins on governance. Decision 1. |
| Build vs adopt the builder | [05](05-ai-assisted-workflow-builders-ui.md): build a thin custom designer | [03](03-durable-workflow-engines-oss-landscape.md): Conductor is already the interpreter plus a UI, pick it if building the interpreter is not worth it | Conductor is the escape hatch, not the default: JVM server, no formal schema, Orkes-steered. |

## The layering every document implies

```
UI / builder   React Flow + CopilotKit/AG-UI, emits IR revisions as JSON Patch   (never executes)
IR             Open Workflow Spec 1.0 profile + x-forjate-* metadata + bindings     (Forjate-owned schema)
Compilers      IR -> Temporal interpreter | Elsa JSON | GH Actions YAML | Conductor | Argo
Engine         Temporal (Go SDK) today; Dapr Workflow as the CNCF alternative
Node runtime   Go: ADK Go 2.0 or Eino; Python: Pydantic AI + TemporalDurability on its own task queue
Agent sandbox  pluggable executor per agent node: Kubernetes Job / Crucible first, Google AX on Agent Substrate later
Tools/models   MCP servers; LiteLLM gateway; OTel GenAI attributes on every span
```

Concrete reuse identified instead of greenfield:

- **Zigflow** (Apache-2.0, Go): Open Workflow YAML executed on Temporal. The "post to Temporal" leg exists; single maintainer, pre-1.0 ([01](01-temporal-as-agent-harness.md), [06](06-portable-workflow-dsl-and-interchange.md)).
- **WorkflowBuilder** (Apache-2.0, React Flow + Temporal plugin): borrow its JSON-Schema-per-node-type binding model, not the product ([05](05-ai-assisted-workflow-builders-ui.md)).
- **act** (MIT, Go): the only thing that executes third-party `uses:` steps outside GitHub; run it inside an ephemeral pod for imported Actions ([02](02-github-actions-schema-as-agent-dsl.md)).
- **actionlint + @actions/workflow-parser** (MIT): validation of imported/exported Actions files ([02](02-github-actions-schema-as-agent-dsl.md)).
- **Open Workflow TypeScript SDK**: renders the DSL to Mermaid, which the research literature shows is a good LLM-facing IR ([05](05-ai-assisted-workflow-builders-ui.md)).
- **gh-aw conventions**: safe-outputs, environment-based approval, commit-both-source-and-lock discipline, as the pattern for the GitHub Actions export ([02](02-github-actions-schema-as-agent-dsl.md)).

## "Google AX" resolved

The name turned out to mean a fourth project, not the three guessed in [04](04-agent-frameworks-deterministic-workflows.md): **github.com/google/ax, Agent Executor** (Apache-2.0, Go, Google-owned, v0.3.1 on 2026-09-25), analysed in [07](07-google-ax-agent-executor.md).

- It is a **runtime for sandboxed agent tasks** on **Agent Substrate** (Apache-2.0, **CNCF Sandbox since October 2026**, gVisor or microVM actors with suspend/resume). Three resources: `Task`, `Workspace` (git, files, MCP servers, skills) and `Model`.
- It is **not a workflow engine** and says so: no edges, dependencies, retries, timers, approvals, outputs or exit status today. Budgets, approval policies and trajectories are roadmap items.
- In the layering it sits **under** the engine as the executor of agent nodes, where a Temporal activity creates a Task and waits for it. It complements Temporal and the Open Workflow IR rather than replacing them.
- Verdict in [07](07-google-ax-agent-executor.md): track, do not build on it yet. Reuse its Workspace shape and runner contract in the harness schema so an AX executor is a plug-in later. Evaluate **kagent** (CNCF Sandbox, also on Substrate) alongside.

The three projects originally analysed remain relevant on their own: Google ADK (node runtime candidate in Go), Genkit (model/tool layer) and ax-llm/ax (unrelated to Google, single maintainer).

## Decisions for Sebas

1. **Engine kernel: Temporal or Dapr Workflow.** Temporal is already a Forjate component, has the richest agent integrations and a UI that is separable by design. Dapr is the only option where engine *and* agent framework are CNCF-governed, at the cost of a sidecar model and a second control plane. Recommendation in the documents: Temporal now, interpreter written so the engine is swappable; Dapr re-evaluated when Dapr Agents has an OSS workflow UI.
2. **Canonical IR: Open Workflow Spec or GitHub Actions schema.** Open Workflow is foundation-governed, has `call: mcp` and `call: a2a` in core, `listen`/`emit`/`wait`/`fork`/`try` for HITL and durability, a Go SDK and a Temporal interpreter. Its risks are Sandbox maturity and a small community. GitHub Actions is what every model writes fluently and what existing CI already is, but it is lossy for durable semantics. Recommendation in the documents: Open Workflow as the IR, GitHub Actions as a first-class importer and exporter.
3. **Builder: build thin or adopt Conductor.** The documents recommend a thin designer (React Flow, Dagre, RJSF, Monaco, Yjs, CopilotKit, AG-UI, Vercel AI SDK through LiteLLM) with compile adapters as plugins. Conductor OSS is the fallback if the interpreter is judged not worth building.
4. **Agent-step executor.** Pluggable from day one: Kubernetes Job or Crucible now; Google AX on Agent Substrate when `v1alpha1` stabilises and exit status, budgets and approvals exist ([07](07-google-ax-agent-executor.md)).
5. **Language split.** Go for interpreter, compilers and the Forjate-owned schema; Python agent activities on a separate task queue only where the Python ecosystem (OpenAI Agents SDK, Pydantic AI) is wanted. Hybrid workers are idiomatic in Temporal.

## Gaps to build regardless of the decisions

- Interpreter workflow with replay tests, `schemaVersion` on every definition and Worker Versioning from day one ([01](01-temporal-as-agent-harness.md)).
- Activity/tool registry with JSON Schemas per node type, MCP and model-gateway adapters.
- Definition store with hash pinning, revisions as JSON Patch, GitOps-applied like other Forjate manifests.
- Token and cost observability: no engine or framework ships it; OTel GenAI semantic conventions are still in Development status.
- Human-approval pattern: Open Workflow has no native human task; model it as `emit` + `listen` with correlation and consider proposing a `human` extension upstream.
- Forjate wiring: ui-server with OIDC, worker HPA, codec server, Argo as the executor for container steps.

## Items flagged as unverified across documents

- Several October-2026 release dates rendered ambiguously by the fetch tool (Tekton 1.18.0, actions/runner 2.338.2, Elsa 3.9.0, Langflow 1.9, ADK Go/TS Agent Config support).
- Tekton's CNCF incubation vote is reported from secondary sources only.
- Open Workflow releases 1.0.1 to 1.0.3 year inferred; `call: mcp` schema stability; SonataFlow coverage of DSL 1.0.
- Whether GitHub's language server tolerates a top-level `x-agent:` key; action compatibility under act outside GitHub.
- Conductor OSS official Helm chart; Hatchet's RabbitMQ requirement; Numaflow's CNCF status; Activepieces copilot CE/EE boundary.

## Suggested next step

Write the ADR for decisions 1 to 3, then scaffold, following the architecture-first approach used for ephemeral use cases: schema and JSON Schema for the IR profile, an interpreter stub with one `intent` node compiling to a TODO activity, a CI gate that validates example definitions, and the builder as a design document before any UI code.

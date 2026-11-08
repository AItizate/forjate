---
title: "Temporal as the execution engine for an agent harness"
date: 2026-10-30
status: research
sources_verified: true
---

# Temporal as the execution engine for an agent harness

## TL;DR

- **Licence is clean**: server, every SDK, CLI, Web UI and Helm chart are MIT (verified via GitHub API, 2026-10-30). `samples-go` is Apache-2.0. No copyleft anywhere in the stack.
- **Governance is single-vendor**: Temporal Technologies owns every repo. Temporal is *not* a CNCF/LF project; the company is only a Gold *member* of the LF-hosted Agentic AI Foundation (2025-12-10). This is the one requirement Temporal does not meet.
- **Declarative DSL on Temporal exists but is thin**: the official `dsl` samples (Go/Python/TS) are ~200-line toy interpreters. The serious option is **Zigflow** (Apache-2.0, Go, v0.18.0 on 2026-10-23), a YAML runtime built on the CNCF Sandbox *Open Workflow Specification* (ex Serverless Workflow). **WorkflowBuilder** (Apache-2.0, 2026-06) adds a React graph editor that executes on Temporal. Nothing ships an "AI-assisted graph builder".
- **Agent tooling is Python-first, Go second**: 10 GA framework integrations (OpenAI Agents SDK GA 2026-03-23, LangGraph, Pydantic AI, Google ADK, Strands...), a Claude tool-calling recipe, MCP recipes, Workflow Streams (2026-05, LLM streaming), External Payload Storage (large prompts). Go has only the Google ADK contrib plugin plus raw SDK.
- **Kubernetes fit is good**: official Helm chart (`temporal-1.7.0`, 2026-09-12) deploys server + separate `ui-server` (gRPC to frontend, OIDC auth, write actions toggleable) — satisfies "UI separated from execution" natively. No official operator; the community `temporal-operator` is Apache-2.0 but one-maintainer.

## Governance and licence table

| Component | Repo | Licence | Owner / governance | Latest version (date) |
|---|---|---|---|---|
| Temporal Server | github.com/temporalio/temporal | MIT | Temporal Technologies (single vendor; no foundation) | v1.32.1 (2026-10-08); v1.31.4 / v1.30.8 patch lines (2026-10-12) |
| Go SDK | temporalio/sdk-go | MIT | Temporal Technologies | v1.50.0 (2026-10-15) |
| Python SDK | temporalio/sdk-python | MIT | Temporal Technologies | 1.35.0 (2026-10-28) |
| TypeScript SDK | temporalio/sdk-typescript | MIT | Temporal Technologies | v1.25.0 (2026-10-27) |
| Temporal CLI (`temporal`) | temporalio/cli | MIT | Temporal Technologies | v1.9.1 (2026-09-14) |
| Web UI + ui-server | temporalio/ui, temporalio/ui-server | MIT | Temporal Technologies | UI v2.57.0 (2026-10-21) |
| Helm chart | temporalio/helm-charts | MIT | Temporal Technologies | temporal-1.7.0 (2026-09-12); temporal-proxy-0.3.0 (2026-10-23) |
| Go samples (incl. `dsl/`) | temporalio/samples-go | Apache-2.0 (Uber/Temporal copyright) | Temporal Technologies | rolling |
| Python samples (incl. `dsl/`) | temporalio/samples-python | MIT | Temporal Technologies | rolling |
| Zigflow (YAML runtime) | github.com/zigflow/zigflow | Apache-2.0 | Independent (Simon Emms, a Temporal staff SA; "not officially maintained by Temporal") | v0.18.0 (2026-10-23) |
| Open Workflow Specification (ex Serverless Workflow) | open-workflow-specification/specification | Apache-2.0 | **CNCF Sandbox** (since 2020-07-14) | DSL 1.0.x |
| WorkflowBuilder | synergycodes/workflowbuilder | Apache-2.0 | Synergy Codes (vendor) | active (2026-10-30 push) |
| temporal-operator | alexandrevilain/temporal-operator | Apache-2.0 | Single maintainer | v0.22.0 (2025-10-31) |
| temporal-ai-agent demo | temporal-community/temporal-ai-agent | MIT | Temporal community org | last push 2026-03-27 |

Verdict on requirement (d): licences pass; **foundation governance fails** for the engine itself. The only foundation-governed piece in the picture is the Open Workflow Specification DSL (CNCF Sandbox), which is a reason to make it Forjate's declarative format regardless of engine.

## 1. Licence and governance

Temporal is a 2019 fork of Uber's Cadence, developed by Temporal Technologies ("a startup by the creators of Cadence", README). The server repo has ~24.1k stars and is MIT; the README does not mention any foundation. The company raised $146M at a $1.72B valuation (2025-03-30) and joined the Linux Foundation's Agentic AI Foundation as a **Gold Member** on 2025-12-10 — membership, not project donation. Net: the code is permissively licensed and relicensing risk is low (MIT, large external user base, Cadence lineage shows forks are viable), but roadmap, release process and trademark are controlled by one commercial entity with a Cloud product.

Release cadence (GitHub API, 2026-10-30): server minor roughly every 3–4 months with three supported patch lines (1.30.x, 1.31.x, 1.32.x all patched in Sept–Oct 2026); SDKs ship monthly (Python 1.30→1.35 between July and October 2026). Big 2025–2026 platform milestones: Workflow Update GA (2025-01-14), Nexus GA (Replay, 2025-03-04), and at Replay 2026 (2026-05-06) Worker Versioning GA, Task Queue Priority GA, Standalone Activities (Public Preview Go/Python/.NET), Workflow Streams (Public Preview), External Payload Storage (Public Preview Python/Go), Rust SDK (Public Preview), Serverless Workers (pre-release).

## 2. Declarative / DSL workflows on Temporal

**Official samples.** `samples-go/dsl`, `samples-python/dsl` and `samples-typescript/dsl-interpreter` are the same toy: a YAML with `variables` and a `root` tree of `sequence` / `parallel` / `activity{name, arguments, result}` statements, unmarshalled and passed *as workflow input* to a single generic `SimpleDSLWorkflow` that walks the tree and calls `ExecuteActivity` by name. There is no conditional, loop, timer, signal, child-workflow or error-handling node. Temporal staff on the community forum describe the pattern as "define a custom DSL in JSON/YAML that becomes input to your workflow, and have an interpreter that translates it into Temporal directives". Temporal's own docs do not promote DSLs; the `workflow-definition` page is exclusively about workflows-as-code.

**How determinism and versioning work with a DSL.** Because the DSL document is *workflow input*, it is recorded in event history and is immutable for that execution — changing the YAML never breaks running executions. What *does* break them is changing the **interpreter** (the Go/Python code that walks the tree), because that changes the sequence of commands on replay. Mitigations, in order of preference: (1) Worker Versioning (GA 2026-05) — pin executions to the worker build that started them; (2) `workflow.GetVersion` / `patched()` inside the interpreter; (3) keep the interpreter small and push semantics into activities. The DSL also needs its own `schemaVersion` so that a stored definition can be validated against the interpreter that will run it. Replay safety also demands that any expression evaluation (`${ .foo }`, jq-style) be pure and that the YAML be parsed deterministically (map ordering).

**Community runtimes.**

- **Zigflow** (Apache-2.0, Go, 231 stars, 670 commits, created 2025-08-01, v0.18.0 on 2026-10-23): "Declarative YAML workflows on Temporal. No SDK boilerplate." Implements the CNCF Open Workflow Specification DSL 1.0 (`document.dsl: 1.0.0`, `do:` list of tasks: `set`, `switch`, `for`, `fork`, `wait`, `listen`, `raise`, `try`, `call: http`, plus a Temporal-specific activity call on a configurable task queue). The `zigflow run -f workflow.yaml` CLI compiles the YAML and registers a worker for the declared `workflowType`/`taskQueue`; definitions are therefore loaded at worker start, not per-execution. Activities can be implemented in any Temporal SDK language. Status per maintainers: "core execution engine and validation pipeline are stable", used "in internal tooling and early adopter environments". It is listed on Temporal's Code Exchange (as "Temporal DSL", the project's former name) but is explicitly independent. No UI.
- **WorkflowBuilder** (Apache-2.0, Synergy Codes, announced on the Temporal forum 2026-06-23): embeddable React Flow editor + a reference backend where "a topological graph runner operates as a Temporal workflow itself, each node executes as an activity"; node definitions are JSON with a JSON Schema that auto-renders the property sidebar; includes human-approval nodes aimed at AI agents. Format is its own JSON graph, not Open Workflow Spec.
- **lainecsmith/temporal-drag-and-drop-dsl** (no licence file, 2 stars): TypeScript proof of concept, not usable.
- **Netflix Maestro** (Apache-2.0, 3.9k stars) and **Conductor** are *separate engines* with their own YAML/JSON DSLs and state stores; neither runs on Temporal. They are alternatives, not layers.

**What exists vs. what must be built:** a stable YAML-to-Temporal compiler exists (Zigflow) but is pre-1.0 and loads definitions at worker start, so "upload a new graph from the UI and run it" needs a runtime-input variant (the official sample pattern) or a worker restart/rollout. No project offers an AI-assisted builder, an activity/tool registry, or definition versioning with migration.

## 3. Temporal for AI agents

Temporal has made agents its flagship use case ("The world's best AI runs on Temporal"). The agent story is **Python-first**.

**Official integrations** (docs.temporal.io/ai, 2026-10-30), all GA unless noted: OpenAI Agents SDK (Python, TypeScript — GA 2026-03-23, now the `temporalio-openai-agents` 1.0 package), LangGraph (Python; blog 2026-07-16 said Public Preview, docs list GA), Deep Agents (Python), Pydantic AI (Python, via `pydantic-ai[temporal]` and a `TemporalDurability` capability maintained by Pydantic), Google ADK (Python, **Go** via `go.temporal.io/sdk/contrib/googleadk`, TypeScript), Google GenAI (Python), Strands Agents (Python, TS), Vercel AI SDK (TS), Mastra (TS), Spring AI (Java). Pattern is identical across them: agent orchestration runs inside the Workflow; every model call and every MCP/tool call becomes an Activity (retries, timeouts, heartbeats); handoffs/sub-agents either stay in-workflow or become Child Workflows.

**Anthropic/Claude**: no plugin, but the AI Cookbook has "Basic agentic loop with Claude and tool calling" (Python) and a "Post-LLM guardrail" recipe using Claude. The recipe's rule of thumb matters for a harness: *disable client-side retries in the Anthropic SDK and let Temporal own retries*. There is no Claude Agent SDK integration; wrapping the Agent SDK's `query()` as a long-running Activity with heartbeats is the obvious adapter to write.

**Platform primitives that map to harness needs:**
- Human-in-the-loop: Signals (fire-and-forget) and **Workflow Update** (GA 2025-01-14; validated, returns a result) — cookbook recipe "Human-in-the-loop AI agent"; Google ADK Go plugin has `ctx.RequestConfirmation` that durably pauses a tool.
- Long loops: Continue-as-New for conversation history; **Workflow Streams** (Public Preview 2026-05) for token streaming via Signals/Updates; **External Payload Storage** (Python/Go preview) for large prompts/outputs; heartbeating Activities for multi-minute LLM calls.
- Sub-agents: Child Workflows or `Agent.as_tool()` (OpenAI) / `SubAgents` (ADK); cross-team/cross-namespace tool services via **Nexus** (GA 2025-03; Python GA, TS/.NET preview as of 2026-05).
- Cost tracking: nothing built in. Token usage must be returned from the model Activity and aggregated in workflow state, exposed via Query/Search Attributes.
- Reference app: `temporal-community/temporal-ai-agent` (MIT, Python, 788 stars, LiteLLM any-provider, Signals for input, Queries for state, MCP, experimental multi-agent).

**Go**: only the ADK contrib plugin is official. Third-party `agenticenv/agent-sdk-go` (tools, MCP, approvals, delegation on Temporal) exists but is early (v0.1.x). No Go recipes in the cookbook.

## 4. Running Temporal on Kubernetes

- **Helm**: `temporalio/helm-charts` is MIT, V3, deploys *only* Temporal services (frontend, history, matching, worker, optional `web` UI and admintools); "the chart does not install any database sub-charts". Persistence: PostgreSQL 12+ (pgx), MySQL 8, Cassandra; visibility via SQL or Elasticsearch 7. Credentials via `existingSecret` ("recommended for production", README). The old "not recommended for production" wording is gone from the current README; the chart is now described as tested by a dedicated pipeline. This matches Forjate's existing `bundles/temporal-stack` (Temporal + PostgreSQL).
- **Operator**: there is **no official or CNCF/kubernetes-sigs operator**. `alexandrevilain/temporal-operator` (Apache-2.0, v0.22.0 on 2025-10-31, 234 stars) provides `TemporalCluster`/`TemporalNamespace` CRDs, cert-manager mTLS, UI/admintools, Istio/Linkerd, version upgrades — but one maintainer and a six-month release gap. Prefer Helm-rendered manifests under Kustomize (Forjate's pattern) over the operator.
- **Postgres vs Cassandra**: Cassandra is the historical default for very high shard counts; Temporal's checklist says throughput is bounded by `numHistoryShards`, which is set once at cluster creation. For a harness (hundreds to low thousands of concurrent agent runs) PostgreSQL with SQL visibility is sufficient and avoids a second stateful system.
- **Workers**: plain Deployments per task queue; scale with HPA on SDK metrics (`temporal_worker_task_slots_available`, schedule-to-start latency) or Temporal's resource-based auto-tuning (GA 2025-03). Worker Versioning (GA 2026-05) gives blue/green worker deployments without breaking in-flight runs.
- **UI separation**: the Web UI is `ui-server` (Go) + SvelteKit frontend, shipped as its own image, connecting to the frontend service over gRPC. Config supports OIDC providers (`auth.providers[].type: oidc`), TLS to the frontend, HTTPS serving, a Codec Server endpoint, and `disableWriteActions` / `startWorkflowDisabled` / per-action toggles. Requirement (a) is met out of the box.
- **Metrics/OTel**: server and SDKs emit Prometheus metrics by default; the docs also support shipping through an OpenTelemetry Collector; SDKs have OTel tracing interceptors; community Grafana dashboards in `temporalio/dashboards`.

## 5. UI layer

The Web UI **does**: browse/filter executions with Search Attributes and Saved Views, event history and timeline, pending activities, workers, schedules, Nexus endpoints, and actions (Signal, Update, Cancel, Reset, Terminate, Pause, "Start Workflow"/"Start Workflow Like This One" with raw JSON input — disabled by `TEMPORAL_START_WORKFLOW_DISABLED`). It **does not**: author, edit or visualize workflow *definitions*, show a graph of a DSL, manage an activity catalogue, or display LLM-specific views (tokens, prompts). It is a debugger, not a builder.

Options for a builder on top:
1. **Temporal gRPC/HTTP API** (`WorkflowService`): StartWorkflow with the DSL document as input, Signal/Update, Query, ListWorkflows with visibility queries. This is what a custom builder backend uses; the `temporal` CLI (MIT) wraps the same API for scripting.
2. **WorkflowBuilder** (Apache-2.0): the only OSS graph editor that runs on Temporal; could be embedded in a Forjate console. Its graph JSON would need a converter to/from the chosen YAML.
3. **Zigflow** has no editor; the Open Workflow Spec community provides JSON Schemas usable to drive a form/graph editor and to validate LLM-generated YAML.
4. **Temporal UI** stays as the ops/debug pane (link from the builder to `/namespaces/{ns}/workflows/{id}`).

## 6. Fit assessment

| Requirement | Fit | Notes |
|---|---|---|
| (a) UI separated from execution | Strong | ui-server is a separate deployable with OIDC; builder UI is a separate app talking gRPC |
| (b) Declarative YAML definitions | Medium | Possible via interpreter workflow; Zigflow gives an Open-Workflow-Spec-compliant compiler; interpreter versioning is the hard part |
| (c) AI-assisted graph-first builder | Weak (build) | Nothing exists; Open Workflow Spec JSON Schema + WorkflowBuilder are the raw materials |
| (d) Permissive licence | Strong | MIT/Apache-2.0 end to end |
| (d) Foundation governance | **Fails** | Single vendor; only the DSL spec is CNCF |

**Strengths**: durable execution with replay is exactly the semantics an agent loop needs (crash-safe tool calls, retries owned by the engine, HITL pauses that cost nothing while waiting); a mature K8s story already present in Forjate; richest AI ecosystem of any OSS orchestrator; Update/Signals/Query, Child Workflows, Nexus, Streams and payload offloading cover every harness primitive.

**Risks**: (1) single-vendor roadmap and Cloud-first feature previews; (2) DSL-interpreter versioning — one careless change to the interpreter non-determinism-fails every in-flight run unless Worker Versioning is adopted from day one; (3) Zigflow is pre-1.0 and one-person; (4) Go agent tooling lag means Go-first requires writing the LLM/MCP activities yourself; (5) history-size limits (50k events / 50 MB) force Continue-as-New design in long agent loops.

**Go-first recommendation** (control, single binary, matches Forjate's Go crucible operator): write a small *generic interpreter workflow* in Go that takes an Open-Workflow-Spec-subset YAML as input (sequence, parallel/fork, switch, for, wait, listen-for-signal/update, call-activity, call-child, try/retry), vendor or depend on Zigflow's parser/validator rather than its worker, and expose activities through a registry keyed by name (`llm.call`, `mcp.tool`, `shell.run`, `k8s.apply`, `claude_agent.run` with heartbeats). Use Worker Versioning plus a `schemaVersion` field. Use the Google ADK Go contrib as a reference for how to wrap model calls and `RequestConfirmation`. Cost: medium; you own every line.

**Python-first recommendation** (fastest to a working agent): a Python interpreter workflow plus `temporalio[openai-agents]` or Pydantic AI for the agent nodes, the Claude cookbook loop for Anthropic, `temporal-ai-agent` as scaffold. Richest tooling, MCP proxies and Streams/External Storage already in preview; weaker for a single-binary control plane. A hybrid — Go control plane/interpreter, Python "agent" activities on their own task queue — is idiomatic Temporal and keeps both advantages.

## Gaps to build

1. **DSL interpreter workflow** (Go): Open Workflow Spec 1.0 subset → Temporal commands; deterministic expression evaluator; `schemaVersion`; Worker Versioning from day one; replay tests (`workflowcheck`, replayer) in CI.
2. **Activity/tool registry**: declarative catalogue (name, JSON Schema in/out, task queue, timeouts, heartbeat, retry policy) that both the interpreter and the builder's LLM read; adapters for Anthropic Messages API, Claude Agent SDK, MCP servers, shell/k8s.
3. **Definition store and versioning**: YAML in Git (Forjate overlay) or a ConfigMap/CRD; pin executions to a definition hash in a Search Attribute.
4. **Builder UI**: graph editor (embed WorkflowBuilder or React Flow) + LLM assistant constrained by the Open Workflow Spec JSON Schema, with "validate → dry-run replay → publish"; start/observe via gRPC; deep-link to Temporal UI.
5. **Agent-specific observability**: token/cost aggregation in workflow state, Search Attributes for model/cost, OTel traces linking Activity spans to LLM calls.
6. **Forjate wiring**: extend `bundles/temporal-stack` with ui-server OIDC, a worker Deployment component with HPA, and a `codec-server` component if payloads are encrypted.

## Sources

- https://github.com/temporalio/temporal (MIT, README, 24.1k stars; releases via GitHub API 2026-10-30)
- https://github.com/temporalio/sdk-go · https://github.com/temporalio/sdk-python · https://github.com/temporalio/sdk-typescript · https://github.com/temporalio/cli · https://github.com/temporalio/ui · https://github.com/temporalio/ui-server (MIT; versions via GitHub API 2026-10-30)
- https://github.com/temporalio/helm-charts (MIT; README)
- https://raw.githubusercontent.com/temporalio/samples-go/main/LICENSE (Apache-2.0) · https://github.com/temporalio/samples-go/tree/main/dsl · https://github.com/temporalio/samples-python/tree/main/dsl · https://github.com/temporalio/samples-typescript/tree/main/dsl-interpreter
- https://community.temporal.io/t/implementing-dsl-workflows/3413 · https://community.temporal.io/t/dsl-implementation-in-go-sdk/14932
- https://docs.temporal.io/workflow-definition (determinism, Worker Versioning vs patching)
- https://github.com/zigflow/zigflow · https://zigflow.dev/docs/intro · https://temporal.io/code-exchange/temporal-dsl
- https://github.com/open-workflow-specification/specification (Apache-2.0, CNCF Sandbox 2020-07-14)
- https://github.com/synergycodes/workflowbuilder · https://community.temporal.io/t/workflowbuilder-open-source-embeddable-react-sdk-for-visual-workflow-editors-runs-on-temporal/19677 (2026-06-23)
- https://github.com/Netflix/maestro (Apache-2.0, separate engine)
- https://docs.temporal.io/ai (integration list) · https://docs.temporal.io/ai/cookbook (Claude, MCP, HITL recipes) · https://docs.temporal.io/ai/cookbook/agentic-loop-tool-call-claude-python
- https://docs.temporal.io/develop/python/integrations/openai-agents · https://temporal.io/blog/announcing-openai-agents-sdk-partnership (2025-07-30; GA 2026-03-23)
- https://temporal.io/blog/temporal-langgraph-plugin-durable-execution (2026-07-16) · https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/ · https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal
- https://docs.temporal.io/develop/go/integrations/google-adk (Go ADK contrib)
- https://github.com/temporal-community/temporal-ai-agent (MIT) · https://pkg.go.dev/github.com/agenticenv/agent-sdk-go
- https://temporal.io/blog/announcing-a-new-operation-workflow-update (GA 2025-01-14)
- https://temporal.io/blog/replay-2025-product-announcements (2025-03-04, Nexus GA) · https://temporal.io/blog/replay-2026-product-announcements (2026-05-06) · https://docs.temporal.io/nexus/use-cases
- https://github.com/alexandrevilain/temporal-operator (Apache-2.0, v0.22.0 2025-10-31)
- https://docs.temporal.io/web-ui · https://docs.temporal.io/references/web-ui-configuration (OIDC, disableWriteActions, startWorkflowDisabled) · https://community.temporal.io/t/start-workflow-button-is-disabled-for-ui-on-docker-and-kubernetes/13740
- https://docs.temporal.io/self-hosted-guide/production-checklist · https://docs.temporal.io/self-hosted-guide/monitoring
- https://www.businesswire.com/news/home/20251210314521/en (Temporal joins AAIF as Gold Member, 2025-12-10) · https://www.businesswire.com/news/home/20250330487137/en ($146M, 2025-03-30)

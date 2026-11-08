---
title: "Portable workflow DSLs and the interchange story for an agent harness"
date: 2026-10-30
status: research
sources_verified: true
scope: "Canonical IR candidates for Forjate's agent harness: CNCF Open Workflow Spec (ex Serverless Workflow), BPMN 2.0, Temporal DSLs, Conductor JSON, GitHub Actions, Argo/Tekton, agent-specific formats, converters"
---

# Portable workflow DSLs and the interchange story for an agent harness

## TL;DR

- **Pick the CNCF Open Workflow Specification (formerly Serverless Workflow) DSL 1.0.x as Forjate's canonical IR.** It is the only candidate that is simultaneously foundation-governed (CNCF Sandbox since 14 Jul 2020), Apache-2.0, JSON/YAML with a published JSON Schema, has a maintained Go SDK (`sdk-go` v4.0.0, 14 Jul 2026), and already ships first-class **`call: a2a`** and **`call: mcp`** tasks plus `listen`/`emit` (CloudEvents), `fork`, `try`/`retry`, `wait` and `run` (container/script/shell/workflow).
- The spec was **renamed on 30 Jun 2026** (issue #1127, PR #1155). Its CNCF status is still **Sandbox**, not Incubating. Flag this as the main governance risk; adoption is real but modest (~950 stars on the spec repo).
- A Go **Open Workflow → Temporal** interpreter already exists (Zigflow, Apache-2.0, by a Temporal solutions architect), so the "post to Temporal" leg is not greenfield. Elsa 3.9 imports BPMN, not Open Workflow, so that leg needs a small compiler; GitHub Actions is a lossy target by construction (no durable timers or mid-run event waits).
- **Conductor JSON** is the strongest runner-up (Apache-2.0, 32k stars, HUMAN/WAIT/DO_WHILE/dynamic fork, native LLM + MCP tasks, Go SDK) but is vendor-governed (Orkes) and schema-less by design. **BPMN 2.0** is the right *prior art* for HITL semantics but the wrong *IR* (XML verbosity for LLMs, bpmn-js watermark licence, Java-centric engines).
- No lossless N-way converter exists anywhere. Design the harness as **one IR + per-executor compilers**, use `metadata` / `x-forjate-*` extension namespaces for executor-specific knobs, and keep jq as the single expression language with a profile for each backend.

## Governance and licence table (verified 30 Oct 2026)

| Format / project | Steward | Governance | Licence | Spec version (date) | Go tooling |
|---|---|---|---|---|---|
| Open Workflow Specification (ex Serverless Workflow) | CNCF Sandbox (since 14 Jul 2020) | Consensus maintainers, CNCF CoC | Apache-2.0 | DSL 1.0.0 (27 Jan 2025); 1.0.1/1.0.2/1.0.3 (31 Jul, year inferred 2025 — verify); `main` references 1.0.4 | `sdk-go` v4.0.0 (14 Jul 2026), partial reference impl; Zigflow (Temporal) |
| BPMN 2.0 / DMN / CMMN | OMG | Standards body, RF-RAND IPR | Spec: royalty-free licence to implement; engines vary | BPMN 2.0.1 (2013) | None notable (engines are Java/.NET) |
| Flowable / Activiti / jBPM-Kogito (BPMN engines) | Flowable AG / Hyland / Apache KIE | Vendor / vendor / ASF | Apache-2.0 (all three) | Flowable 2025.1 agent engine (22 Jul 2025) | No |
| bpmn-js (editor) | Camunda Services GmbH | Vendor | **bpmn.io licence (MIT-derived, watermark must remain visible)** | — | No |
| Camunda 8 / Zeebe | Camunda | Vendor | Camunda License 1.0 (source-available, non-OSI) since 8.6 — **fails the filter** | 8.7 agentic orchestration (8 Apr 2025) | Go client only |
| Elsa Workflows 3 | Elsa community (Sipke Schoorstra) | Single-maintainer OSS | MIT | 3.9.0 adds BPMN 2.0 import (date unverified; after 3.8.3) | No (.NET) |
| Conductor OSS | conductor-oss (Orkes primary maintainer) | Vendor-led OSS, ex Netflix | Apache-2.0 | Rolling; LLM/MCP tasks present 2026 | `conductor-oss/go-sdk` (Apache-2.0, fluent workflow builder + workers) |
| Netflix Maestro | Netflix | Single vendor | Apache-2.0 (open-sourced 23 Jul 2024) | YAML/JSON/Python DSL | No (Java 21) |
| Temporal DSL sample | Temporal | Vendor sample, not supported | MIT (samples) | Sample only | Go sample interpreter |
| GitHub Actions workflow schema | GitHub | Vendor | Schema on SchemaStore (Apache-2.0); runner MIT | Rolling | `nektos/act` (MIT) runs a subset |
| Argo Workflows | CNCF **Graduated** (Argo, Dec 2022) | CNCF | Apache-2.0 | v3.x stable, v4.1 referenced 2026 | Native Go (CRDs, client) |
| Tekton Pipelines | CNCF **Incubating** (vote closed 24 Mar 2026, moved from CDF) | CNCF | Apache-2.0 | v1 API | Native Go |
| Oracle Open Agent Spec | Oracle | Single vendor | Apache-2.0 + UPL-1.0 | arXiv 2510.04173 (Oct 2025) | No (PyAgentSpec) |
| Letta Agent File (.af) | Letta | Single vendor | Apache-2.0 | 2025 | No |
| Google ADK Agent Config | Google | Single vendor | Apache-2.0 | Experimental; ADK Python ≥1.11 (Aug 2025) | No (Python; Java loader) |
| Microsoft Agent Framework declarative workflows | Microsoft | Single vendor | MIT | Preview, docs updated 26 Oct 2026 | No (.NET/Python, PowerFx) |
| AAIF (Autonomous Agent Interchange Format) | Observalytics SL | Individual IETF draft, not endorsed | — | draft-00, 25 Jun 2026 | No |

## 1. CNCF Open Workflow Specification (ex Serverless Workflow)

**Status and governance.** Approved as a CNCF Sandbox project on 14 Jul 2020, originating from the CNCF Serverless Working Group. It has **not** moved to Incubating; the only TOC artefact found is the original sandbox proposal. The rename from "Serverless Workflow" to "Open Workflow Specification" was proposed 10 Nov 2025 (issue #1127) because the DSL "spans far beyond serverless"; CNCF Legal approved the name and the change landed 30 Jun 2026 (PR #1155). The GitHub org is now `open-workflow-specification`, the site `open-workflow-specification.org`, and the old `serverlessworkflow.io` / netlify URLs 301-redirect. The rename was explicitly "branding only, no API or schema change". Licence: Apache-2.0 on every repo (specification, SDKs, editor, migration tool).

**Versions.** 1.0.0 shipped 27 Jan 2025 after five years and five alphas; it merged "states" and "actions" into a single recursive **task** concept. Point releases 1.0.1 (expressions in HTTP query/headers), 1.0.2 (**new `a2a` and `mcp` call tasks**, Lemline added as runtime) and 1.0.3 (stdin/argv for `run`, container pull policy) are all dated 31 Jul on the releases page; the year is not shown and I infer 2025 (the A2A PR #1114 pre-dates the Nov 2025 rename issue) — **verify before quoting**. The `dsl-reference.md` on `main` already refers to **1.0.4**, unreleased.

**DSL shape.** A document (`dsl`, `namespace`, `name`, `version`, optional `input`/`output` schemas, `timeout`, `schedule`, `use` for reusable auth/functions/retries/catalogs) followed by a `do` list of named tasks. Task kinds: `call` (http, openapi, grpc, asyncapi, **a2a**, **mcp**, or a custom function from a catalog), `run` (container, script — JavaScript ES2024 or Python 3.13 —, shell, workflow), `do`, `fork` (with `compete: true` for race semantics), `for`, `switch`, `try`/`catch` with `retry` (count/duration limits, constant/linear/exponential backoff, jitter), `listen` (consume CloudEvents with `one|any|all` strategies, filters and correlation), `emit` (publish CloudEvents), `wait` (ISO 8601 duration), `set`, `raise`. Each task has `if`, `input.from`, `output.as`, `export.as` and a `then` flow directive (`continue|exit|end|<taskName>`). The spec also defines lifecycle events (workflow/task started, suspended, resumed, retried, faulted, completed) as CloudEvents, and `extensions` that intercept tasks before/after — this is the sanctioned hook for cross-cutting concerns (tracing, cost accounting, policy).

**Expression language.** jq by default, `${ ... }` in strict mode; context variables `$workflow.input`, `$context`, `$task`, `$item`/`$index`. Errors follow RFC 7807 Problem Details.

**Ecosystem.** Runtimes listed by the spec: Synapse (.NET, Apache-2.0, ~314 stars, dashboard + API + `synctl`), Apache KIE SonataFlow (Kubernetes operator; KIE 10.1.0 on 1 May 2025, 10.2.0 on 29 Mar 2026 — its DSL 1.0 coverage is not confirmed in the docs I read; historically it implements 0.8), **Quarkus Flow** (Red Hat/Quarkiverse, implements 1.0.0 with a Java fluent API 1:1 to the tasks and LangChain4j integration), the Java SDK reference implementation, and **Lemline** (Quarkus runtime, **BUSL-1.1 — excluded** by the filter). SDKs: Go (v4.0.0 after the rename; v3.1.0 was the first with spec 1.0 and a partial reference implementation), Java 7.x, TypeScript 1.0.x, .NET, Python (1.0 status unclear; an open issue asked for it), PHP, Rust (alpha). Tooling: VS Code extension, a new React Flow-based **web visual editor** (`open-workflow-specification/editor`, Apache-2.0, embeddable, Mermaid export, ELK auto-layout), a `migration-tool` from 0.8/0.9 to 1.x, and the JSON Schema in `schema/workflow.yaml`.

**Agentic signals.** Three distinct ones: (i) the `a2a` and `mcp` call tasks in the core spec (proposed by Huawei's team; A2A uses JSON-RPC `message/send`, `tasks/get` against an agent card; MCP covers tools, prompts and resources with the initialisation handshake); (ii) the Java SDK merged an **Agentic DSL** on 19 Sep 2025 (PR #785: `sequence()`, `parallel()`, `loop()` over LangChain4j `AgenticScope`, `AgentTaskConfigurer`); (iii) FOSDEM 2025 talk positioning "agentic AI" as the growth area. There is no `agent` task kind; an LLM call is modelled as `call: http|openapi` against a gateway or `call: a2a` against an agent.

**Assessment as canonical IR.** Strong fit: declarative, recursive, schema-validated, small vocabulary (12 task kinds) that an LLM can author reliably, CloudEvents for both input (`listen`) and output (`emit`), explicit retry/timeout objects, `run: workflow` for composition, and `metadata` on workflow and task for annotations. Gaps: no first-class "human task" (model it as `emit` + `listen` with correlation, which is also how Temporal signals map); no typed compensation/saga construct; Sandbox-only maturity; the Go SDK is "partial reference implementation", so Forjate would rely on Zigflow or write its own interpreter for Temporal.

## 2. BPMN 2.0, DMN, CMMN (OMG)

The OMG grants a fully-paid, perpetual, worldwide licence to use the specification to create and distribute software; BPMN 2.0.1 is under the RF-RAND IPR mode, so implementing it is royalty-free. Permissive engines: **Flowable** (Apache-2.0; its 2025.1 release on 22 Jul 2025 added a first-class Agent Engine beside BPMN/CMMN/DMN with "AI Agent Task" elements, Utility/Knowledge agents and a Guardrail Agent in 2026.1), **Activiti** (Apache-2.0), **jBPM/Kogito** (Apache-2.0, now Apache KIE). Camunda 8/Zeebe is source-available (Camunda License 1.0) and its agentic orchestration (8.7, 8 Apr 2025) is built on **ad-hoc sub-processes** so an agent picks tasks inside a bounded scope — excellent prior art for "deterministic outside, non-deterministic inside", but the engine fails the licence filter. **Elsa 3.9.0** imports BPMN 2.0 XML, binds tasks to Elsa activities and re-exports; the docs are explicit it is "not a promise of complete BPMN-tool compatibility" (release date not verified).

Editors: **bpmn-js** uses the bpmn.io licence, MIT-derived but with a clause that the watermark linking to bpmn.io "MUST NOT be removed or changed" and must stay fully visible — acceptable for an internal UI, a red flag for a white-labelled Forjate console; removal requires a commercial agreement with Camunda. Camunda Modeler (desktop) is MIT but embeds bpmn-js with the same term.

Fit for HITL agent workflows: BPMN's User Task, boundary timer/message/error events, event sub-processes, compensation and ad-hoc sub-process are the most complete vocabulary for human-in-the-loop and exception handling of any candidate. Downsides as an IR: XML with `bpmndi` diagram interchange is roughly 5–10x the tokens of an equivalent YAML task list and LLMs frequently emit non-well-formed sequence-flow references; semantics live in engine-specific extension elements (`flowable:`, `camunda:`, `zeebe:`), so "portable BPMN" is portable only at the shape level; all serious engines are Java or .NET.

## 3. Temporal DSLs, Netflix Maestro and Conductor JSON

**Temporal sample DSL.** `temporalio/samples-go/dsl` defines `variables` plus a `root` statement that is one of `activity{name, arguments, result}`, `sequence{elements}`, `parallel{branches}`. That is the whole grammar: no conditionals, loops, timers, signals, retries or child workflows; variables are a flat string map. It is a teaching sample, not a format. The TypeScript repo has an equivalent `dsl-interpreter`. The community filled the gap: Temporal's Code Exchange lists **Temporal DSL** by Simon Emms (Staff SA, Temporal EMEA), explicitly "implements the Serverless Workflow DSL", not endorsed by Temporal; the project is **Zigflow** (`mrsimonemms/zigflow`, Go, Apache-2.0, ~230 stars, 670 commits) which compiles Open Workflow 1.0+ YAML into Temporal workflows with HTTP activities, external activities in any SDK language, loops, try/catch, child workflows, signals/queries, schedules and waits. There is also a 2022 community thread asking for exactly this ("Temporal workflow definition from serverlessworkflow JSON").

**Netflix Maestro** (Apache-2.0, 23 Jul 2024, Java 21, ~3.9k stars) has YAML, JSON and Python DSLs with foreach, subworkflow, conditional and signal steps; it is optimised for data/ML pipelines at Netflix scale (500k jobs/day) and has no HITL construct or Go SDK. Interesting for the foreach-at-scale design, not as an IR.

**Conductor JSON** (`conductor-oss/conductor`, Apache-2.0, ~32.4k stars, Orkes is the primary maintainer). Workflow definitions are versioned JSON with `tasks[]`; system tasks: HTTP, INLINE (script), EVENT, WAIT (duration or until), **HUMAN**, KAFKA_PUBLISH, JSON_JQ_TRANSFORM, NO_OP; operators: FORK_JOIN, **FORK_JOIN_DYNAMIC**, JOIN, SWITCH, **DO_WHILE**, SUB_WORKFLOW, START_WORKFLOW, SET_VARIABLE, TERMINATE, DYNAMIC; and in 2026 native **LLM tasks** (chat/text completion, embeddings, vector search, content generation) plus `LIST_MCP_TOOLS` / `CALL_MCP_TOOL` across 14+ providers. Data flows via `${task_ref.output.path}` expressions (JSONPath-like, not jq). Go SDK with a fluent workflow builder and worker runner, Apache-2.0. Assessment: the most *operationally* battle-tested JSON DSL in the list and the only one with HUMAN as a first-class task — but it is a product's wire format, not a specification: no independent JSON Schema or conformance suite, vocabulary grows with Orkes' roadmap, and governance is single-vendor. Good as a **target**, risky as the **source of truth**.

## 4. GitHub Actions, Argo Workflows, Tekton

**GitHub Actions** (depth in the sibling report). As an IR: pros are universal familiarity, `nektos/act` for local execution, matrix fan-out, `needs` DAG, `if` conditions and environments with required reviewers as a crude approval gate. Cons: the model is "jobs on ephemeral runners" — no durable timers (max 6h per job, 35 days per run), no mid-run `listen` for an external event, retries are per-step shell idioms, expressions (`${{ }}`) are a proprietary mini-language, and state between steps is via files or `GITHUB_OUTPUT`. A lossless GH Actions → Open Workflow mapping is realistic (jobs → `fork`, steps → `do`, `needs` → ordering, `if` → `if`, matrix → `for`); the reverse is lossy for `listen`, `wait` > hours, `emit`, retry policies and correlation. **GitHub Agentic Workflows** (`gh-aw`) is instructive: Markdown with YAML frontmatter (`on`, `permissions`, `tools`, `safe-outputs`, `timeout-minutes`) compiled by `gh aw compile` into `.lock.yml` Actions files — i.e. GitHub itself treats Actions as a *compilation target*, not an authoring format.

**Argo Workflows** (CNCF Graduated with the Argo project, Dec 2022; Apache-2.0; Go). Templates: container, script, resource, **suspend** (manual or timed resume via CLI/API/UI — a usable HITL primitive), http, containerSet; composition via `steps` and `dag`, loops via `withItems`/`withParam`/`withSequence`, conditionals via `when`, `retryStrategy` with backoff, `onExit` handlers, `synchronization`, and cron. Everything is a Kubernetes CRD, so it fits Forjate's Kustomize-first philosophy and is the natural executor for the `run: container` task kind. Limitation: expressions are `expr` templates on `{{ }}` and payloads are strings/artifacts, not JSON documents.

**Tekton Pipelines** (Apache-2.0; graduated at the CDF 26 Oct 2022; accepted as **CNCF Incubating** by TOC vote closed 24 Mar 2026 — reported by secondary sources, verify against `cncf/toc`). Tasks/Pipelines/`when`/`finally`/`matrix`, but no suspend/human task and no event wait; it is a CI DSL first.

## 5. Agent-specific workflow formats

- **Google ADK Agent Config** (Apache-2.0, experimental, ADK Python ≥1.11.0 / Java ≥0.3.0, introduced Aug 2025): `root_agent.yaml` with `name`, `model`, `instruction`, `tools`, `sub_agents`; Sequential/Parallel/Loop agents; Gemini-only, `LangGraphAgent`/`A2aAgent` unsupported. Describes *agents*, not *workflows*.
- **Microsoft Agent Framework declarative workflows** (MIT, preview, docs 26 Oct 2026): `kind: Workflow` + `actions[]` with ~30 action kinds (`SetVariable`, `If`, `ConditionGroup`, `Foreach`, `GotoAction`, `InvokeAzureAgent`, `InvokeMcpTool`, `HttpRequestAction`, `Question`, `RequestExternalInput`, `EndWorkflow`), **PowerFx** expressions (`=Concat(...)`), namespaces `Local.*`, `Workflow.Inputs.*`, `System.*`. Copilot Studio agents are the sibling `.mcs.yml` assets synced via the VS Code extension. Closest vendor analogue to what Forjate wants, including HITL, but PowerFx and `InvokeAzureAgent` tie it to Microsoft.
- **Oracle Open Agent Spec** (Apache-2.0 + UPL, arXiv 2510.04173, Oct 2025): JSON/YAML; `Agents` and `Flows` with LLM/tool nodes; runtime adapters for WayFlow, LangGraph, AutoGen, CrewAI; LangChain lists it as an integration (`open_agent_spec`). Pitches itself as "ONNX for agents". Python-only, single vendor, young.
- **Letta Agent File (.af)** (Apache-2.0, Apr 2025): serialises a *stateful agent* (memory blocks, tools, model config) — portability of agent state, not control flow.
- **AAIF** (IETF individual draft-00, 25 Jun 2026, Observalytics SL): JSON Schema 2020-12 for agent identity, objectives, model routing, orchestration topology, tool catalogs, policies; explicitly "not endorsed by the IETF". Watch, do not depend.
- **Dify DSL** (YAML app export since v0.6; Dify is Apache-2.0 with additional terms), **n8n JSON** (Sustainable Use License, fails filter; several third-party transpilers exist: nCode → Python, n8n2LangGraph, n8n2py), **Langflow JSON** (MIT, nodes + edges), **Flowise** (Apache-2.0, `flowData` stringified JSON), **CrewAI** (MIT, `agents.yaml` + `tasks.yaml`) — all are app-specific graphs whose node types are the product's component catalogue; none is a neutral IR.
- **OpenAI AgentKit / Agent Builder** exports workflows as **Agents SDK code** (TypeScript or Python), not as a declarative document; the migration guide confirms "Code → Agents SDK" is the only export path.
- **GitHub Agentic Workflows frontmatter** (covered above) is the one format where natural-language prompt and deterministic trigger/permission metadata coexist in a single file; Forjate's UI could borrow the "prose body + typed frontmatter" split for the LLM steps while keeping the control flow typed.

Conclusion for this section: the "agent" formats describe *what an agent is*; the *orchestration* formats describe *how steps run*. Only Open Workflow (via `a2a`/`mcp`), Conductor (LLM/MCP tasks) and Microsoft's declarative workflows sit in both camps, and only the first is foundation-governed.

## 6. Compilation and interchange

**Existing converters (all partial).** Open Workflow → Temporal: Zigflow (Go, Apache-2.0). Serverless Workflow 0.8 → 1.0: official `migration-tool`. BPMN → Serverless Workflow: only side-by-side comparison documents in the spec repo (`comparisons/`), no tool. BPMN → Elsa: Elsa 3.9 importer. GitHub Actions → Argo: nothing maintained found; `act` runs Actions locally instead of translating them. n8n → Python/LangGraph: community transpilers with "LLM-assisted fallback for unsupported nodes", a telling sign of lossiness. Make → n8n converter exists. Nothing targets Conductor from a neutral IR; Conductor's own SDKs are the "compiler".

**Where lossiness appears.**

| Concern | Open Workflow | Temporal (code) | Conductor | GH Actions | Argo |
|---|---|---|---|---|---|
| Durable timer (days) | `wait` | `workflow.Sleep` | WAIT | **lost** (6h/35d caps) | suspend `duration` |
| External signal / HITL | `listen` + correlation | Signal / Update | HUMAN, WAIT | **approx.** (environment reviewers) | suspend + resume API |
| Retry semantics | `retry` policy object | `RetryPolicy` on activity | per task-def | **lost** (shell loops) | `retryStrategy` |
| Parallel fan-out | `fork` / `for` | goroutines + `Await` | FORK_JOIN(_DYNAMIC) | matrix / parallel jobs | `withParam` |
| Expressions | jq | host language | `${}` JSONPath-ish | `${{ }}` | `{{ }}` + `expr` |
| Events out | `emit` CloudEvents | activity | EVENT / KAFKA_PUBLISH | **approx.** (`repository_dispatch`) | sidecar/exit handler |

The expression layer is the real interchange hazard: jq ↔ JSONPath ↔ GH expressions ↔ PowerFx are not bijective. Two mitigations: (1) adopt a **jq profile** in the IR (path access, `select`, `map`, arithmetic, string interpolation) that each backend can either evaluate natively (Zigflow/Temporal and Conductor's JSON_JQ_TRANSFORM both ship gojq/jq) or compile down; (2) for GH Actions and Argo, run a tiny `forjate-eval` CLI step that evaluates jq against the task context, which keeps the semantics identical at the cost of one extra step.

**Extension namespaces.** Open Workflow allows `metadata` on the workflow and on every task, and its JSON Schema does not forbid additional properties there; the convention from OpenAPI/AsyncAPI is `x-<vendor>-<key>`. Forjate should reserve `x-forjate-temporal` (task queue, activity options, heartbeat), `x-forjate-argo` (template, resources, node selector), `x-forjate-github` (runner labels, environment), `x-forjate-elsa` (activity type) and `x-forjate-agent` (model, gateway route, token budget, tool allowlist). Compilers read their own namespace and ignore the rest; a `metadata`-free document must still compile to every backend (the core must be sufficient). Validation: base schema from the spec + a Forjate overlay schema that constrains `metadata` keys — both run in the UI before "post".

**Feasibility verdict.** A "common IR → N backends" compiler is realistic if the IR is the *smallest* of the candidates and executors are allowed to reject documents (`listen` on GitHub Actions should fail at compile time with a clear message, not silently poll). Zigflow demonstrates the Temporal leg; Argo is a straightforward structural mapping; Conductor is a 1:1 mapping for everything except `extensions`; Elsa needs a plugin that maps task kinds to activities (its BPMN importer is the template); GH Actions is a strict subset.

## 7. Recommendation

**Canonical IR: Open Workflow Specification DSL 1.0.x (CNCF), YAML-first with JSON Schema validation, jq profile, `x-forjate-*` metadata.** Forjate already ships Temporal; adopting Zigflow (or forking its interpreter into a Forjate component) gives an immediate executor, Argo gives a Kubernetes-native second executor for `run: container`, and Conductor/Elsa/GitHub Actions become optional compile targets. Model LLM steps as `call: http` against the Forjate gateway (or `call: openapi` on its spec) and tool calls as `call: mcp`; model human approval as `emit` + `listen` with correlation on a `requestId`. Contribute upstream a proposal for a `human` extension or a canonical "approval" pattern — the project is small enough that a Forjate maintainer can shape it, which is itself a reason to pick it.

| Criterion | Open Workflow (CNCF) | Conductor JSON | GH Actions schema | Custom schema |
|---|---|---|---|---|
| Governance | CNCF Sandbox, Apache-2.0 | Vendor (Orkes), Apache-2.0 | Vendor (GitHub) | Forjate only |
| LLM-friendliness | High: 12 task kinds, YAML, schema | Medium: verbose JSON, 25+ task types | High | High (you design it) |
| HITL / durable semantics | `listen`/`wait`/`emit`; no native human task | HUMAN, WAIT native | Weak | Whatever you implement |
| Agent constructs | `a2a`, `mcp` in core | LLM + MCP tasks | None | Must invent |
| Go tooling | sdk-go v4 + Zigflow | go-sdk | act (runner) | None |
| Existing executors | Synapse, Quarkus Flow, SonataFlow, Zigflow/Temporal | Conductor only | GitHub, act | None |
| Interchange risk | Low (spec + schema + conformance features) | Medium (product format) | High (lossy) | Highest (isolated) |
| Main risk | Sandbox maturity, small community | Vendor roadmap, no formal schema | Semantics tied to runners | Zero ecosystem |

### Example (Open Workflow DSL 1.0.x, Forjate annotations)

```yaml
document:
  dsl: '1.0.0'
  namespace: forjate
  name: triage-and-release
  version: '0.3.0'
  metadata: { x-forjate-temporal: { taskQueue: harness }, x-forjate-argo: { serviceAccount: harness } }
use:
  retries:
    llm: { delay: { seconds: 2 }, backoff: { exponential: {} }, limit: { attempt: { count: 4 } } }
do:
  - plan:
      try:
        - draft:
            call: http
            with: { method: post, endpoint: https://gateway.forjate.svc/v1/chat,
                    body: { model: '${ $workflow.input.model }', input: '${ .issue }' } }
            metadata: { x-forjate-agent: { tokenBudget: 20000 } }
      catch: { errors: { with: { type: https://serverlessworkflow.io/spec/1.0.0/errors/communication } }, retry: llm }
  - gather:
      fork:
        compete: false
        branches:
          - repo: { call: mcp, with: { server: { endpoint: http://mcp-github:8080 }, tool: get_pull_request, arguments: { id: '${ .issue.pr }' } } }
          - ci:   { call: mcp, with: { server: { endpoint: http://mcp-github:8080 }, tool: list_check_runs, arguments: { id: '${ .issue.pr }' } } }
  - askHuman:
      emit: { event: { with: { type: forjate.approval.requested.v1, source: /harness, data: { requestId: '${ $workflow.id }', summary: '${ .plan.summary }' } } } }
  - waitForApproval:
      listen: { to: { one: { with: { type: forjate.approval.decided.v1, correlate: { requestId: { from: '${ .data.requestId }', expect: '${ $workflow.id }' } } } } } }
      timeout: { after: { days: 3 } }
  - decide:
      switch:
        - approved: { when: '${ .[0].data.decision == "approve" }', then: release }
        - rejected: { then: end }
  - release:
      run: { container: { image: ghcr.io/forjate/releaser:1.4, command: 'release ${ .issue.pr }' } }
      metadata: { x-forjate-argo: { template: releaser }, x-forjate-github: { environment: production } }
  - done:
      emit: { event: { with: { type: forjate.release.completed.v1, source: /harness, data: '${ . }' } } }
```

Unverified items to close before committing: the exact year of releases 1.0.1–1.0.3; whether SonataFlow executes DSL 1.0 today or only 0.8; the Elsa 3.9.0 release date; Tekton's CNCF incubation vote (secondary sources only); the `mcp` call schema stability (added in a pre-release tag).

## Sources

- Open Workflow Specification repo: https://github.com/serverlessworkflow/specification (redirects to open-workflow-specification)
- Org page: https://github.com/open-workflow-specification
- 1.0.0 release post (27 Jan 2025): https://open-workflow-specification.org/blog/releases/release-100
- Releases: https://github.com/open-workflow-specification/specification/releases
- DSL reference (main): https://raw.githubusercontent.com/serverlessworkflow/specification/main/dsl-reference.md
- Rename issue #1127: https://github.com/serverlessworkflow/specification/issues/1127
- A2A call PR #1114: https://github.com/serverlessworkflow/specification/pull/1114
- Java SDK Agentic DSL PR #785: https://github.com/serverlessworkflow/sdk-java/pull/785
- sdk-go v4.0.0: https://github.com/open-workflow-specification/sdk-go/releases/tag/v4.0.0
- Visual editor: https://github.com/open-workflow-specification/editor
- Synapse: https://github.com/serverlessworkflow/synapse
- Quarkus Flow: https://docs.quarkiverse.io/quarkus-flow/dev/specification.html
- SonataFlow: https://kie.apache.org/docs/10.2.x/sonataflow/serverlessworkflow/1.43.0.Final/cloud/index.html
- Lemline (BUSL-1.1): https://github.com/lemline/lemline
- Zigflow: https://github.com/mrsimonemms/zigflow ; Temporal Code Exchange: https://temporal.io/code-exchange/temporal-dsl
- Temporal DSL sample: https://github.com/temporalio/samples-go/tree/main/dsl
- Temporal community thread: https://community.temporal.io/t/temporal-workflow-definition-from-serverlessworkflow-json-definition/7414
- Conductor OSS: https://github.com/conductor-oss/conductor ; tasks: https://docs.conductor-oss.org/devguide/concepts/tasks ; Go SDK: https://github.com/conductor-oss/go-sdk
- Netflix Maestro: https://github.com/Netflix/maestro ; open-sourcing news: https://gigazine.net/gsc_news/en/20240723-netflix-workflow-orchestrator-maestro/
- bpmn.io licence: https://bpmn.io/license/ ; forum clarification: https://forum.bpmn.io/t/license-type-clarification-commercial-use/6443
- OMG BPMN 2.0.1 and IPR: https://omg.org/spec/BPMN/2.0.1 ; https://scancode-licensedb.aboutcode.org/omg-bpmn-2.0.html
- Camunda 8.7 agentic orchestration (8 Apr 2025): https://camunda.com/blog/2025/04/camunda-87-agentic-orchestration-for-enterprise/
- Flowable 2025.1 agent engine (22 Jul 2025): https://www.newsfilecorp.com/release/259603/ ; docs: https://documentation.flowable.com/latest/reactmodel/agent/introduction/
- Flowable/Activiti/jBPM licences: https://awesome.ecosyste.ms/projects/github.com%2Fflowable%2Fflowable-engine ; https://en.wikipedia.org/wiki/Activiti_(software) ; https://www.jbpm.org/code/license.html
- Elsa BPMN authoring and interchange: https://docs.elsaworkflows.io/guides/bpmn-authoring-and-interchange
- Argo graduation: https://codefresh.io/blog/argo-project-graduates-with-unanimous-support ; concepts: https://argo-workflows.readthedocs.io/en/release-3.5/workflow-concepts/
- Tekton: https://tekton.dev/blog/2022/10/26/tekton-graduation/ ; CNCF incubation report (secondary): https://machineherald-io.pages.dev/article/2026-04/02-tekton-joins-the-cncf-as-an-incubating-project-after-seven-years-of-kubernetes-native-cicd-development
- GitHub Agentic Workflows frontmatter: https://github.github.com/gh-aw/reference/frontmatter-full/
- Google ADK Agent Config: https://adk.dev/agents/config/
- Microsoft Agent Framework declarative workflows: https://learn.microsoft.com/en-us/agent-framework/workflows/declarative
- Oracle Open Agent Spec: https://github.com/oracle/agent-spec ; paper: https://arxiv.org/html/2510.04173v2 ; LangChain integration: https://docs.langchain.com/oss/python/integrations/providers/open_agent_spec
- Letta Agent File: https://github.com/letta-ai/agent-file
- AAIF IETF draft: https://datatracker.ietf.org/doc/draft-schemacommons-aaif/
- OpenAI Agent Builder export: https://developers.openai.com/api/docs/guides/agent-builder/migrate-from-agent-builder
- Dify DSL: https://docs.dify.ai/en/guides/management/app-management ; n8n export: https://docs.n8n.io/workflows/export-import ; Langflow: https://docs.langflow.org/concepts-flows-import ; Flowise: https://docs.flowiseai.com/using-flowise/prediction.md ; CrewAI: https://docs.crewai.com/concepts/tasks
- n8n transpilers: https://github.com/opsingh861/nCode ; https://github.com/sw30labs/.github/wiki/n8n2langraph.stub

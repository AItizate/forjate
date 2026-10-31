---
title: "AI-assisted workflow builders and UI building blocks for a decoupled Forjate designer"
date: 2026-10-30
status: research
sources_verified: true
notes: "Licences verified against repo LICENSE files on 2026-10-30 unless marked 'unverified'. Release dates taken from GitHub release pages; where GitHub omitted the year (current-year releases) it is marked 'inferred'."
---

# AI-assisted workflow builders & UI building blocks (graph first, wiring later)

## TL;DR

- **No existing OSS builder gives Forjate the full combination** of (a) permissive licence, (b) designer decoupled from runtime, (c) executor-agnostic export, and (d) a self-hostable AI copilot. The closest are **Synergy Codes WorkflowBuilder** (Apache-2.0, React Flow + Temporal plugin, JSON-Schema-driven node forms) and **Elsa Studio** (MIT, Blazor designer talking to Elsa Server over HTTP), but both bind to one executor and neither ships an open AI loop.
- The AI copilots that are mature (n8n, Sim, Kestra EE, Windmill) are either behind restrictive licences (Sustainable Use, AGPL) or run as **vendor-hosted services** even when the product is self-hosted (Sim's `COPILOT_API_KEY` is issued by sim.ai; n8n's builder is cloud-only; Kestra OSS copilot is Gemini-only).
- The UI building blocks are all clean: **React Flow / Svelte Flow (MIT, xyflow 12.12.0 / 1.7.0, Sep 2026)**, **Dagre (MIT)**, **ELK (EPL-2.0)**, **Monaco (MIT)**, **Mermaid (MIT)**, **RJSF (Apache-2.0)**, **CopilotKit + AG-UI (MIT)**, **Vercel AI SDK (Apache-2.0)**, **Yjs (MIT)**. Flag: **tldraw** (custom non-OSS since Dec 2023) and **bpmn-js** (MIT + mandatory watermark clause).
- Research (MermaidFlow ICML 2025, AFlow ICLR 2025, Flow ICLR 2025, GPTSwarm ICML 2024) converges on the pattern Forjate wants: **LLM edits a declarative, statically-verifiable graph IR; a validator/repair loop gates each revision; implementation is bound afterwards.** Mermaid-as-IR is specifically shown to beat code-as-IR on verifiability.
- **Recommendation:** build a thin custom designer (React Flow + a Forjate "Intent Graph" YAML IR aligned with CNCF **Open Workflow Specification 1.0** + CopilotKit chat loop + JSON-Schema validate/repair), with **compile adapters** to Temporal (via Zigflow DSL or a DSL interpreter), Elsa JSON, GitHub Actions YAML and Conductor JSON as plugins. Reuse WorkflowBuilder's JSON-Schema-node pattern and the Open Workflow TypeScript SDK's Mermaid export rather than any whole product.

---

## Comparison matrix (governance + licence first)

Legend: ✅ ok · ⚠️ caveat · ❌ fails hard filter · ❓ unverified

| Project | Governance | Licence (verified 2026-10-30) | AI graph builder | Declarative def. | Designer ≠ runtime | Export / external executors | Maturity |
|---|---|---|---|---|---|---|---|
| **Node-RED** 5.0.9 (21 Oct 2026) | OpenJS Foundation | ✅ Apache-2.0 | ⚠️ community plugins only (`node-red-contrib-llm-plugin`, `node-red-semantic-flow-language`) | ✅ flow JSON | ❌ editor is served by the runtime | ❌ Node-RED only | High |
| **Elsa Studio / Elsa 3.9.0** (4 Oct, year inferred 2026) | Single vendor (Elsa Workflows OSS) | ✅ MIT | ❌ none | ✅ Elsa JSON | ✅ Blazor RCL talks to Elsa Server API; sidecar/iframe/standalone hosting | ❌ Elsa only | Medium-high; Studio dev moving into `elsa-core/studio/` |
| **WorkflowBuilder** (Synergy Codes) | Single vendor | ✅ Apache-2.0 (CE); EE add-ons separate | ⚠️ "AI Studio" templates + AI-agent nodes; not a prompt→graph copilot | ✅ JSON, node forms from JSON Schema | ✅ `@workflowbuilder/sdk` usable standalone; Temporal plugin separate | ⚠️ Temporal plugin (1 Activity per node); other executors = write your own | Early (426★) |
| **Zigflow + Zigflow Studio** | Single maintainer | ✅ Apache-2.0 | ❌ | ✅ YAML (Open Workflow Spec DSL) | ✅ Studio is a separate repo | ⚠️ Temporal only, but DSL is CNCF-spec shaped | Early (231★ / 9★) |
| **Conductor OSS** | Orkes + community (not a foundation) | ✅ Apache-2.0 | ❌ | ✅ JSON | ⚠️ UI ships with server, but is a separate React app | ❌ Conductor only | High |
| **Argo Workflows** | CNCF Graduated | ✅ Apache-2.0 | ❌ | ✅ YAML CRDs | n/a: UI is viewer + YAML submit; no visual editor (Meshery Kanvas adds one) | ❌ Argo only | High |
| **Open Workflow Spec** (ex-Serverless Workflow) 1.0 + editor | CNCF Sandbox | ✅ Apache-2.0 | ❌ | ✅ YAML/JSON DSL | ✅ VS Code editor / `editor` repo decoupled; SDK → Mermaid | ✅ spec is runtime-neutral (SonataFlow, Synapse, Zigflow→Temporal) | Spec stable; renamed Jul 2026 (sdk-go v4.0.0) |
| **Kestra 2.0** | Single vendor | ✅ Apache-2.0 (core) | ✅ Copilot: prompt→YAML, diff-style partial edits, revisions | ✅ YAML | ❌ UI inside server | ❌ Kestra only | High; OSS copilot = Gemini only, multi-provider is EE |
| **Flowise 3.x** (Workday-owned since Aug 2025) | Single vendor | ⚠️ Apache-2.0 + commercial `enterprise/` dir | ✅ Agentflow "sparkles" generator (prompt→nodes+edges) | ✅ JSON | ❌ | ❌ | High |
| **Langflow 1.12.x** (DataStax/IBM) | Single vendor | ✅ MIT | ✅ Langflow Assistant + MCP "Flow DevOps" tools (1.9, Mar 2026 ❓) | ✅ JSON | ⚠️ MCP server lets external agents build flows | ❌ runs on Langflow | High |
| **Sim** | Single vendor | ✅ Apache-2.0 | ✅ Copilot builds/edits/debugs; **but Copilot is a sim.ai-hosted service (`COPILOT_API_KEY`)** | ✅ JSON | ❌ | ❌ | Medium |
| **Activepieces** | Single vendor | ⚠️ MIT + `packages/ee/` commercial | ⚠️ Copilot in builder (EE-leaning ❓) | ✅ JSON | ❌ | ❌ | High |
| **Open Agent Platform** (LangChain) | Single vendor | ✅ MIT | ⚠️ no-code agent config | ⚠️ | ✅ UI vs LangGraph Platform | ❌ | **Archived 25 Feb 2026** |
| **n8n** | Single vendor | ❌ Sustainable Use 1.0 | ✅ AI Workflow Builder (PH launch 14 Oct 2025); cloud-only, credit-metered | ✅ n8n JSON (de-facto LLM-known format) | ❌ | ❌ | High |
| **Dify 1.16** | Single vendor | ❌ Modified Apache-2.0 (no multi-tenant, keep branding) | ⚠️ community DSL generators only | ✅ YAML DSL 0.7 | ❌ | ❌ | High |
| **Windmill** | Single vendor | ❌ AGPL-3.0 (+ proprietary EE) | ✅ AI flow chat builds steps, wires inputs, loops/branches | ✅ | ❌ | ❌ | High |
| **Automatisch / Budibase / Huginn** | Single vendor | ❌ AGPL-3.0 / ❌ GPL-3.0 / ✅ MIT | ❌ | – | ❌ | ❌ | Huginn legacy |
| **Vercel Workflow DevKit** (beta Oct 2025) | Single vendor | ✅ MIT | ❌ code-first (`"use workflow"`) | ❌ | n/a | ❌ | Beta |
| **GitHub Agentic Workflows (gh-aw)** | GitHub (Microsoft) | ✅ MIT | ✅ Markdown intent → `gh aw compile` → `.lock.yml` | ✅ MD+frontmatter → Actions YAML | ✅ compile step is separate | ✅ target is plain GitHub Actions | 5.5k★, "production" |
| OpenAI AgentKit / Google Opal / MS Foundry Workflows / Copilot Studio | Proprietary | ❌ not OSS (prior art) | ✅ prompt→canvas, canvas↔YAML/code | ✅ | ✅ (Foundry: Visual↔YAML two-way) | ⚠️ code/YAML export only to own SDK | GA/preview |
| **tldraw SDK** | Single vendor | ❌ custom non-OSS since Dec 2023 (1.x stays MIT) | – | – | – | – | – |
| **bpmn-js / Camunda Modeler** | Camunda | ⚠️ MIT + non-removable watermark clause | – | ✅ BPMN XML | ✅ | ✅ BPMN engines | High |

---

## Part A — existing AI-assisted builders

### Automation/workflow products with an AI copilot

**n8n** (❌ Sustainable Use Licence v1.0: internal business / non-commercial only). The AI Workflow Builder (launched Oct 2025) does prompt→draft workflow with real-time build feedback and conversational refinement; every create/modify/run costs one credit (Trial 20, Starter 50, Pro 150 per month). It is cloud-only; n8n stated a self-hosted decision for Q1 2026 but nothing shipped is verified. What *is* reusable is the **n8n JSON format**: it is probably the workflow format LLMs know best, and it is emitted by third-party skills/MCP servers. Forjate cannot embed n8n, but an **n8n-JSON import adapter** is cheap and useful (Forjate already ships n8n as a component).

**Kestra 2.0** (✅ Apache-2.0 core). The most disciplined copilot in the group: Ask / Edit / Plan modes in a sidebar; "Copilot changes only the part you ask about"; each accepted change becomes a flow revision; output is **validated YAML** before apply. In OSS only Gemini is supported; Anthropic/OpenAI/Ollama/etc. are Enterprise. Designer is embedded in the server. Good *pattern* reference (partial edits + revision history + validation gate), poor fit as a reusable UI.

**Windmill** (❌ AGPL-3.0). AI flow chat builds flows step by step, reuses hub scripts, wires inputs between steps and creates loops/branches with iterator expressions. Strong UX reference for "progressive binding" (it picks an existing script or generates one per step), licence excludes it.

**Sim** (✅ Apache-2.0, Sim Studio Inc.). Copilot "builds, edits, tests, debugs, deploys" workflows from chat inside the canvas. Crucially, **Copilot is a Sim-managed service**: self-hosters must generate a `COPILOT_API_KEY` at sim.ai (known docker-compose issue #1324 where the key is not injected). So the designer is OSS but the AI loop is SaaS — exactly the dependency Forjate wants to avoid.

**Flowise 3.x** (⚠️ Apache-2.0 with a commercial `enterprise/` directory; Workday acquisition Aug 2025 raises governance risk). Agentflow V2 has a sparkles button: describe → nodes and connections generated → review. Monolithic runtime, LangChain-centric node vocabulary.

**Langflow** (✅ MIT; DataStax/IBM). Langflow 1.9 (Mar 2026, ❓ date from secondary source) added the Langflow Assistant and an MCP server that lets *any* MCP-capable agent create flows, add components and wire tools. The MCP-driven "agent builds the graph through tools" approach is relevant prior art for a tool-calling copilot, but the graph is Langflow's runtime graph.

**Activepieces** (⚠️ MIT except `packages/ee/` and `packages/server/api/src/app/ee`). Has a Copilot in the builder; which side of the EE line it falls on is unverified — treat as EE until checked.

**Dify** (❌ modified Apache-2.0: no multi-tenant operation without written consent, frontend branding may not be removed). No first-party prompt→workflow generator found; the ecosystem of "Dify DSL generator" skills confirms the LLM-edits-YAML-DSL pattern works in practice (DSL 0.7, Dify 1.16, Jul 2026).

**Open Agent Platform** (MIT) was archived 25 Feb 2026 in favour of LangSmith Agent Builder — remove from consideration.

**Node-RED 5.0.9** (✅ Apache-2.0, **OpenJS Foundation** — the only foundation-governed builder with a mature visual editor). No core AI generation; two community plugins exist: `@background404/node-red-contrib-llm-plugin` (sidebar chat with Ollama, sends existing flows for modification, "Import Flow" button for LLM-emitted JSON) and `node-red-semantic-flow-language` (natural-language → flow JSON). The editor is served by the runtime and the flow JSON is tightly bound to installed node modules, so it is not a decoupled designer — but the *flow JSON + import-from-LLM* loop is proven, and Node-RED is already a Forjate component (candidate export target, not UI).

### Designers that are structurally decoupled from execution

**Elsa Studio / Elsa Workflows 3.9.0** (✅ MIT). Blazor Razor Class Library; hosts as WebAssembly, Blazor Server, embedded, iframe or standalone and talks to **Elsa Server over its HTTP API** (sidecar architecture in the docs). This is precisely "UI separated from execution" — but the designer's activity catalogue comes from the server, the definition is Elsa JSON, there is no AI layer, and it is .NET/Blazor (hard to embed in a React/Next stack). Studio development is being consolidated into `elsa-core/studio/`. Verdict: keep as an **executor target** (Elsa is already on Forjate's list) and as architectural prior art, not as the shared UI.

**WorkflowBuilder (Synergy Codes)** (✅ Apache-2.0, Synergia Pro Sp. z o.o. 2025-2026). Embeddable React SDK on React Flow; nodes defined by your own node types with **properties panels generated from JSON Schema**; diagrams saved as JSON to your API/callback; a separate **Temporal plugin** runs "one Activity per node" with one registered executor per node type, plus human-approval pause/resume and live run monitoring. "AI Studio" ships AI-agent nodes and AI templates (mistral-small demo), not a conversational graph builder. This is the closest existing artefact to Forjate's target architecture; the Temporal binding model (node type → executor) is exactly "progressive binding".

**Zigflow** (✅ Apache-2.0, 231★) is a YAML DSL for Temporal that implements the CNCF Open Workflow Specification DSL (`document.dsl: 1.0.0`, `do:` list of tasks: activity call, HTTP, `for`, `switch`, wait, child workflow, signals, queries) and interprets it in a generic Temporal workflow. **Zigflow Studio** (Apache-2.0, 9★, 28 commits) is a nascent drag-and-drop UI in a separate repo. Small, but it is the only project that already gives Forjate "CNCF-standard YAML → Temporal" for free.

Also found: Temporal's own `samples-go/dsl` (YAML sequence/parallel of activities interpreted by one workflow), the community thread "DSL workflow design", and `temporal-build-flows.vercel.app` (visual → YAML → typed Python; ❓ provenance/licence unverified). No Temporal-official visual designer exists.

**Conductor OSS** (✅ Apache-2.0, Orkes-maintained; not under a foundation). `ui-next` has a visual editor (drag/drop tasks, parameters) over a JSON definition; `orkes-workflow-visualizer` library since 3.21.11. JSON is the source of truth, so Conductor is an easy compile target.

**Argo Workflows** (✅ Apache-2.0, CNCF Graduated). The Argo UI is a viewer plus YAML submit / template forms; there is no first-party visual editor. Meshery Kanvas offers a drag-and-drop designer for Argo CRDs (Apache-2.0, ❓ depth not verified). Argo is a straightforward YAML compile target.

**Open Workflow Specification** (✅ Apache-2.0, CNCF Sandbox, formerly Serverless Workflow; renamed around Jul 2026 — sdk-go v4.0.0, 14 Jul; error URIs moved to open-workflow-specification.org). The spec has a VS Code extension (Apache KIE/SonataFlow) and an `editor` repo that render the DSL as **Mermaid** and update the diagram live from the code; the TypeScript SDK exposes `toMermaidCode()`. This is a ready-made text IR with a graph renderer and multiple runtimes (SonataFlow, Synapse, Zigflow→Temporal).

**BPMN tooling**: bpmn-js is MIT **plus** a clause that the bpmn.io watermark "MUST NOT be removed or changed" and must stay visible; Camunda Modeler is MIT but bundles bpmn-js/dmn-js/form-js under that licence. Acceptable only if the watermark is acceptable; BPMN semantics are also heavier than an intent graph needs.

### Proprietary prior art (not candidates)

- **OpenAI AgentKit / Agent Builder** (Oct 2025): canvas of agent/tool/logic nodes that maps 1:1 to Agents SDK primitives and **exports to Python/TypeScript**. Pattern: canvas → code export to one SDK.
- **Google Opal** (Jul 2025, 160+ countries Nov 2025): describe → editable visual workflow; conversational and visual modes round-trip.
- **Microsoft Foundry Agent Service multi-agent workflows** (preview 25 Nov 2025): **Visual ↔ YAML views, any change in one updates the other**; VS Code round trip. The cleanest public demonstration of two-way canvas/text sync.
- **Copilot Studio**: topics/actions stored as `.mcs.yaml`, exportable via solutions, VS Code extension with IntelliSense/validation.
- **GitHub Agentic Workflows (gh-aw)** (✅ MIT, 5.5k★): Markdown intent + YAML frontmatter → `gh aw compile [--validate --strict]` → hardened `.lock.yml` Actions workflow; both source and lock are committed. This is the "intent first, compiled wiring later" split, in text form, targeting GitHub Actions — directly reusable as one of Forjate's compile targets.

---

## Part B — building blocks for a custom designer (licences verified)

| Block | Licence | Notes |
|---|---|---|
| **React Flow / Svelte Flow** (`@xyflow/react` 12.12.0, `@xyflow/svelte` 1.7.0, 24 Sep 2026) | MIT (webkid GmbH) | De-facto standard; used by Langflow, Flowise, WorkflowBuilder, Temporal Playground. Pro examples are paid but the library is MIT. |
| **Vue Flow** | MIT (webkid + Burak Cakmakoglu) | Vue port of the same model. |
| **Rete.js** | MIT | Dataflow/processing-oriented; heavier abstraction than needed for an intent graph. |
| **Drawflow** | MIT (Jero Soler) | Tiny, vanilla JS; low maintenance activity — fallback only. |
| **Dagre** | MIT (Chris Pettitt) | Simple layered layout; maintenance sporadic but sufficient for DAGs. |
| **ELK / elkjs** | EPL-2.0 (Eclipse) | Better layouts (ports, hierarchy). EPL-2.0 is weak-copyleft at file level; fine to consume as a dependency in an Apache-2.0 project, do not fork it in-tree. |
| **Monaco Editor** | MIT (Microsoft) | YAML/JSON/TS editing in the wiring phase; JSON-Schema-driven completion via `monaco-yaml`. |
| **Mermaid** | MIT (Knut Sveidqvist) | Text IR LLMs edit well; render-only (no editing semantics), so use it as an *exchange* format, not the store. |
| **Excalidraw** | MIT | Freeform sketching; not a graph model — optional "napkin" phase. |
| **tldraw SDK** | ❌ custom non-OSS (Dec 2023; 2.x/3.x/4.x need trial/commercial/hobby licence; 1.x MIT) | Exclude. |
| **react-jsonschema-form (RJSF)** | Apache-2.0 (rjsf-team) | Node configuration forms from JSON Schema — same trick WorkflowBuilder uses. |
| **CopilotKit** | MIT (Atai Barkai) | Chat ↔ app-state loop; `useCopilotReadable` (expose graph) + `useCopilotAction` (LLM calls add/remove/connect node) is exactly the chat→canvas pattern. |
| **AG-UI** | MIT | Event protocol between agent backend and UI; lets the copilot backend be any framework (LangGraph, Agents SDK, Mastra...) and keeps the UI decoupled from the LLM runtime. |
| **Vercel AI SDK** | Apache-2.0 (Vercel) | Provider-agnostic streaming/tool-calling; `generateObject` with a Zod/JSON schema is the natural "generate graph diff" primitive; pairs with LiteLLM (already in Forjate) as the provider gateway. |
| **Yjs** | MIT (Kevin Jahns / RWTH Aachen) | CRDT for multi-user editing of the graph doc; also gives free undo/redo and revision snapshots. |
| **Open Workflow TypeScript SDK** | Apache-2.0 | Typed builders + validation + `toMermaidCode()` for the spec DSL. |
| **Elsa Studio components** | MIT | Blazor-only; not reusable in a React shell except via iframe. |

---

## Part C — design patterns for "graph first, wiring later"

**1. Text-first intermediate representation.** Every system that does this well keeps a declarative text artefact as the source of truth and treats the canvas as a projection: Kestra (YAML), Foundry (YAML↔visual two-way), gh-aw (Markdown→YAML), Copilot Studio (`.mcs.yaml`), Open Workflow (YAML→Mermaid). LLMs edit text diffs far more reliably than they manipulate canvas state, and text diffs are reviewable and versionable. Mermaid is good as an *LLM-facing* view (MermaidFlow shows it is more verifiable than code), but it lacks typed node config, so the canonical store should be a schema'd YAML/JSON document from which Mermaid is derived.

**2. Schema validate → repair loop.** Generate (structured output against the IR's JSON Schema) → validate (schema + graph invariants: single start, reachability, no dangling edges, typed ports) → feed violations back → regenerate only the offending fragment. Kestra's "Copilot changes only the part you ask about" and gh-aw's `--validate --strict` are the production versions; MermaidFlow's "safety-constrained graph evolution" is the research version. Reject-and-retry is cheap because the IR is small.

**3. Intent nodes with no implementation.** A node in revision 1 is `{id, kind: intent, title, intent: "...", inputs?, outputs?}` and nothing else. Only the graph shape, the per-node intent and the I/O contracts are iterated. This mirrors Flow (ICLR 2025: workflows as activity-on-vertex graphs refined at runtime) and AutoFlow (natural-language program as the workflow format, optimised iteratively).

**4. Progressive binding.** Once the shape is frozen, each intent node is bound to a `binding`: a Temporal activity type, an Elsa activity, a GitHub Action `uses:`, a Conductor task type, an MCP tool, an LLM prompt, or a human-approval gate. Windmill's "reuse a hub script or generate one" and WorkflowBuilder's "one executor per node type" are the two existing UX forms. Binding is itself LLM-assisted (suggest candidates from the registered activity/tool catalogue) but gated by a typed schema per binding kind.

**5. Round-tripping canvas ↔ text.** Keep both edit surfaces writing to the same document (Yjs doc holding the YAML AST or a JSON model); layout coordinates live in a sidecar `ui:` block so compiled output ignores them. Foundry's two-way sync and the Open Workflow VS Code editor ("change in the code editor, the diagram updates automatically") are the references.

**6. Compile targets.** The IR compiles to:
- **Temporal**: either emit Zigflow/Open-Workflow YAML and run it with Zigflow's interpreter worker, or ship a Forjate DSL interpreter workflow (pattern from `samples-go/dsl`) where each bound node → Activity, `switch` → conditional, `for` → child workflows/loops, human gate → signal + timer.
- **Elsa**: emit Elsa 3 workflow-definition JSON (activities + connections + variables) and `POST` to Elsa Server's definitions API; Elsa Studio becomes the *runtime* inspector.
- **GitHub Actions**: DAG → jobs with `needs:`; intent nodes bound to `uses:`/`run:`; agent nodes compile through gh-aw-style frontmatter → `.lock.yml`.
- **Conductor**: JSON `tasks[]` with `SIMPLE`, `SWITCH`, `FORK_JOIN`, `HUMAN`.
- **Argo**: `Workflow` CRD with `dag.tasks[]` + `dependencies`.
Unsupported constructs per target (e.g. Actions has no durable human-wait) are surfaced as compile errors in the designer before anything is posted.

**Papers (brief):** GPTSwarm (ICML 2024) — agents as optimisable graphs where each node is an LLM/tool op; AFlow (ICLR 2025) — MCTS over code-represented workflows with execution feedback (+5.7% over SOTA); AutoFlow (2024) — natural-language program as workflow format, iteratively optimised; FlowMind (2024, J.P. Morgan) — prompt recipe grounding LLM-generated workflows in reliable APIs; WorkflowLLM (2024) — data-centric fine-tuning for orchestration; Flow (ICLR 2025) — AOV-graph workflows refined dynamically; MermaidFlow (ICML 2025) — Mermaid as verifiable IR with safety-constrained evolutionary edits, beating ADAS/AFlow by 2–5.5%. The consistent lesson: **a declarative, statically checkable graph IR plus an edit–verify loop outperforms free-form code generation.**

---

## Recommendation for Forjate

**Option 1 — adopt an existing OSS builder as the UI.** Only two pass the licence *and* decoupling bar: Elsa Studio (MIT, but Blazor and Elsa-only, no AI) and WorkflowBuilder (Apache-2.0, React Flow, JSON-Schema nodes, Temporal plugin, no conversational builder, single small vendor, 426★). Node-RED is the only foundation-governed option but its editor is welded to its runtime. None gives multi-executor export or an open AI loop; adopting one means forking its definition format and bolting a copilot on anyway.

**Option 2 — thin custom designer with executor adapters as plugins (recommended).**

- **Shell:** Next.js/React + **React Flow** (MIT) + **Dagre** (MIT; ELK later) + **RJSF** (Apache-2.0) for node config + **Monaco** (MIT) for the wiring view. Collaboration/undo via **Yjs** (MIT).
- **IR:** a Forjate "Intent Graph" YAML document whose `do:`/task vocabulary is a *profile* of the **CNCF Open Workflow Specification 1.0** (Apache-2.0, foundation-governed) extended with `intent` tasks and a `bindings:` section; `ui:` sidecar for layout. Mermaid view generated by the Open Workflow TypeScript SDK for LLM reading and for docs.
- **AI loop:** **CopilotKit** (MIT) in the UI, **AG-UI** (MIT) to the copilot backend, **Vercel AI SDK** (Apache-2.0) `generateObject` against the IR JSON Schema, routed through **LiteLLM** (already a Forjate component) so any model works self-hosted. Backend applies the validate→repair loop and emits graph *patches* (JSON Patch) rather than whole documents; each accepted patch is a revision.
- **Executor adapters** (`forjate-compile-*` plugins, pure functions IR → target + POST client): Temporal (Zigflow YAML or Forjate DSL interpreter), Elsa JSON, GitHub Actions YAML (reusing gh-aw conventions for agent steps), Conductor JSON, Argo YAML, plus an **importer** for n8n JSON and Node-RED flow JSON so existing automations in the cluster can be brought in.
- **Borrow, don't fork:** WorkflowBuilder's JSON-Schema-per-node-type + one-executor-per-node-type binding model; Kestra's partial-edit + revision UX; gh-aw's commit-both-source-and-lock discipline; Foundry's two-way visual/YAML view.

**Compile sketch.** `intent` node → (Temporal) `call: activity` with `activityType` from binding, retries from node policy; (Elsa) activity object of the bound type + `connections[]` from edges; (Actions) job with `needs:` from incoming edges and `uses:`/`run:` from binding; unbound intents compile to a failing step in Actions, a `TODO` stub activity in Temporal/Elsa, so revision-1 graphs can still be posted and visualised in the target UI.

**Open items / unverified:** Activepieces copilot CE-vs-EE boundary; Langflow 1.9 date; Elsa 3.9.0 year (inferred 2026); `temporal-build-flows.vercel.app` provenance; Meshery Kanvas Argo editor depth; whether n8n shipped a self-hosted builder in 2026.

---

## Sources

- n8n: https://docs.n8n.io/build/ways-of-building-workflows/ai-workflow-builder · https://raw.githubusercontent.com/n8n-io/n8n/master/LICENSE.md · https://www.producthunt.com/p/n8n-io/n8n-ai-workflow-builder
- Dify: https://raw.githubusercontent.com/langgenius/dify/main/LICENSE · https://github.com/langgenius/dify/releases
- Flowise: https://raw.githubusercontent.com/FlowiseAI/Flowise/main/LICENSE.md · https://docs.flowiseai.com/using-flowise/agentflowv2 · https://blog.flowiseai.com/coming-soon
- Langflow: https://raw.githubusercontent.com/langflow-ai/langflow/main/LICENSE · https://pypi.org/project/langflow-builder-mcp/0.1.0/
- Sim: https://raw.githubusercontent.com/simstudioai/sim/main/LICENSE · https://docs.sim.ai/copilot · https://github.com/simstudioai/sim/issues/1324
- Open Agent Platform: https://github.com/langchain-ai/open-agent-platform (archived 2026-02-25)
- Activepieces: https://raw.githubusercontent.com/activepieces/activepieces/main/LICENSE · https://www.activepieces.com/docs/license
- Node-RED: https://raw.githubusercontent.com/node-red/node-red/master/LICENSE · https://github.com/node-red/node-red/releases · https://flows.nodered.org/node/@background404/node-red-contrib-llm-plugin · https://flows.nodered.org/node/node-red-semantic-flow-language
- Kestra: https://raw.githubusercontent.com/kestra-io/kestra/develop/LICENSE · https://kestra.io/docs/ai-tools/ai-copilot · https://kestra.io/docs/whats-new-2-0
- Elsa: https://raw.githubusercontent.com/elsa-workflows/elsa-studio/main/LICENSE · https://github.com/elsa-workflows/elsa-core/releases · https://docs.elsaworkflows.io/getting-started/architecture-overview · https://docs.elsaworkflows.io/guides/studio/integration
- Windmill: https://raw.githubusercontent.com/windmill-labs/windmill/main/LICENSE · https://www.windmill.dev/changelog/ai-flow-chat
- Automatisch/Huginn/Budibase: https://automatisch.io/docs/other/license · https://raw.githubusercontent.com/Budibase/budibase/master/LICENSE
- Vercel Workflow DevKit: https://github.com/vercel/workflow · Vercel AI SDK licence https://raw.githubusercontent.com/vercel/ai/main/LICENSE
- Google Opal: https://developers.googleblog.com/en/introducing-opal/
- OpenAI AgentKit: https://osher.com.au/blog/openai-agentkit/ · https://www.educative.io/courses/building-with-openai/np/visual-development-with-the-agent-builder
- Microsoft Foundry workflows: https://devblogs.microsoft.com/foundry/introducing-multi-agent-workflows-in-foundry-agent-service/ · https://learn.microsoft.com/azure/foundry/agents/concepts/workflow
- Copilot Studio YAML: https://learn.microsoft.com/en-us/microsoft-copilot-studio/visual-studio-code-extension-edit-agent-components
- GitHub Agentic Workflows: https://github.com/githubnext/gh-aw · https://blog.frankel.ch/agentic-github-workflows/
- Temporal: https://github.com/temporalio/samples-go/tree/main/dsl · https://community.temporal.io/t/dsl-workflow-design/985 · https://community.temporal.io/t/workflowbuilder-open-source-embeddable-react-sdk-for-visual-workflow-editors-runs-on-temporal/19677 · https://temporal-build-flows.vercel.app/ (unverified)
- WorkflowBuilder: https://github.com/synergycodes/workflowbuilder · https://raw.githubusercontent.com/synergycodes/workflowbuilder/main/LICENSE
- Zigflow: https://github.com/zigflow/zigflow · https://github.com/zigflow/studio · https://dev.to/mrsimonemms/zigflow-the-missing-temporal-dsl-5bfm
- Conductor: https://raw.githubusercontent.com/conductor-oss/conductor/main/LICENSE · https://github.com/conductor-oss/conductor · https://www.orkes.io/content/developer-guides/build-workflows-using-ui
- Argo: https://argo-workflows.readthedocs.io/ · https://layer5.io/cloud-native-management/meshery/integrations/argo-workflows
- Open Workflow Specification (ex-Serverless Workflow): https://github.com/open-workflow-specification/specification · https://github.com/open-workflow-specification/sdk-go/releases/tag/v4.0.0 · https://github.com/serverlessworkflow/specification/issues/1127 · https://github.com/serverlessworkflow/sdk-typescript · https://kie.apache.org/docs/10.0.x/sonataflow/serverlessworkflow/latest/tooling/serverless-workflow-editor/swf-editor-vscode-extension.html
- BPMN: https://raw.githubusercontent.com/bpmn-io/bpmn-js/main/LICENSE · https://github.com/camunda/camunda-modeler · https://forum.bpmn.io/t/bpmn-js-license-watermark-doubt/11267
- tldraw: https://tldraw.dev/blog/license-update-for-the-tldraw-sdk · https://isitreallyfoss.com/projects/tldraw
- Building blocks: https://raw.githubusercontent.com/xyflow/xyflow/main/LICENSE · https://github.com/xyflow/xyflow/releases · https://raw.githubusercontent.com/retejs/rete/main/LICENSE · https://raw.githubusercontent.com/jerosoler/Drawflow/master/LICENSE · https://raw.githubusercontent.com/bcakmakoglu/vue-flow/master/LICENSE · https://raw.githubusercontent.com/dagrejs/dagre/master/LICENSE · https://raw.githubusercontent.com/kieler/elkjs/master/LICENSE.md · https://raw.githubusercontent.com/microsoft/monaco-editor/main/LICENSE.txt · https://raw.githubusercontent.com/mermaid-js/mermaid/develop/LICENSE · https://raw.githubusercontent.com/excalidraw/excalidraw/master/LICENSE · https://raw.githubusercontent.com/rjsf-team/react-jsonschema-form/main/LICENSE.md · https://raw.githubusercontent.com/CopilotKit/CopilotKit/main/LICENSE · https://raw.githubusercontent.com/ag-ui-protocol/ag-ui/main/LICENSE · https://raw.githubusercontent.com/yjs/yjs/main/LICENSE
- Papers: GPTSwarm https://proceedings.mlr.press/v235/zhuge24a.html · AFlow https://arxiv.org/abs/2410.10762 · AutoFlow https://arxiv.org/abs/2407.12821 · FlowMind https://arxiv.org/abs/2404.13050 · WorkflowLLM https://arxiv.org/abs/2411.05451 · Flow https://arxiv.org/abs/2501.07834 · MermaidFlow https://arxiv.org/abs/2505.22967

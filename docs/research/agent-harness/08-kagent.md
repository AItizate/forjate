---
title: "kagent: CNCF agent control plane on Kubernetes, evaluated as the agent-step layer of the harness"
date: 2026-10-30
status: research
sources_verified: true
verification_method: "Shallow clone of kagent-dev/kagent (HEAD 12aa4d4, 2026-10-30) read directly: README, docs/architecture/*, CRD schemas in helm/kagent-crds, go/api/a2a, Helm values; GitHub API for licence, stars, releases, org repos; kagent-dev/community MAINTAINERS.md; CNCF project page; Solo.io and CNCF blog posts."
---

# kagent

Evaluated because Agent Substrate's README names it, next to Google AX, as the other runtime built on Substrate, and because it is the only **foundation-governed** project in this research that models agents declaratively on Kubernetes. Companion to [07](07-google-ax-agent-executor.md); same question: where does it fit in a harness whose control loop is a deterministic workflow?

## TL;DR

- **kagent is an agent control plane, not a workflow engine.** It defines *agents* as CRDs (`Agent`, `AgentTemplate`, `Harness`, `ModelConfig`, `RemoteMCPServer`, `SandboxTemplate`, `EgressPolicy`), compiles them into immutable revisions, runs them as Substrate actors, and exposes them over **A2A** (invoke), **gRPC** (sessions, checkpoints, sandboxes) and **MCP**. Composition between agents is LLM-routed (in-process subagents, remote A2A calls), never a declared DAG. The repo has no workflow, DAG or pipeline construct.
- **Governance is the best in this research for an agent runtime:** CNCF Sandbox since 2025-05-22, incubation application in due diligence, Apache-2.0, OpenSSF Best Practices badge, public MAINTAINERS list. Caveat: 7 of 8 maintainers are Solo.io employees and Solo.io sells "Solo Enterprise for kagent" on top.
- **Version 1.0 is landing right now and changes everything underneath.** `v1.0.0-rc1` was tagged on 2026-10-30; it replaces the Deployment-based runtime of `v0.10.x` with **Agent Substrate**, PostgreSQL and a new API group `api.kagent.dev/v1alpha3`. The project says the transition "will include breaking changes".
- **It already has what AX lacks and a harness needs from an agent step:** typed outputs (`outputSchema`, structured output over A2A), a framework-neutral **human-in-the-loop extension** (tool approval and ask-user, as A2A `input-required`), per-tool `requireApproval`, token usage events, checkpoints and forks, OTel tracing, a Helm chart, a UI, and model providers including Ollama and any OpenAI-compatible gateway (LiteLLM fits).
- **Verdict:** stronger candidate than AX for the **agent-step executor** of the harness, and a natural Forjate component once 1.0 is GA. Still not the deterministic control loop: Temporal (or Dapr) stays on top, with an activity that drives a kagent A2A task and maps `input-required` to a workflow signal.

## Governance and licence table

| Item | Value (verified 2026-10-30) |
|---|---|
| Repo | github.com/kagent-dev/kagent, created 2025-01-21 by Solo.io |
| Licence | Apache-2.0 (LICENSE in repo; GitHub SPDX) |
| Foundation | **CNCF Sandbox**, accepted 2025-05-22; incubation application under due diligence (secondary sources) |
| Maintainers | 8 listed in kagent-dev/community: 7 Solo.io, 1 Amdocs; CODEOWNERS teams `maintainers`, `developers`, `ui-maintainers` |
| Commits since 2026-07 by domain | 14 noreply, 11 solo.io, 3 gmail, 2 giantswarm.io |
| Stars / forks / open issues | 4.1k / 870 / 238 |
| Releases | `v1.0.0-rc1` 2026-10-30; `v1.0.0-alpha17` 2026-10-21; `v0.10.4` 2026-10-21 (legacy line still maintained) |
| Languages | Go (controller, Go ADK, CLI), Python (ADK, LangGraph/CrewAI/OpenAI integrations), TypeScript (UI: React + antd, no graph canvas) |
| Sibling repos | kmcp (MCP server lifecycle, 476★), khook (Kubernetes events → agent, 43★), a2a-go (NOASSERTION licence, flag), byo-ext (community harnesses, empty), OpenShell |
| Commercial layer | Solo Enterprise for kagent (2025-09-15): agentgateway integration, identity/policy model, "AgentOps" dashboard, HITL controls. agentgateway itself is Linux Foundation |
| Dependencies at 1.0 | Agent Substrate (CNCF Sandbox, gVisor or microVM), PostgreSQL, Helm, cert-manager-style pod certificates; see [07](07-google-ax-agent-executor.md) for Substrate's weight |

## 1. The model

Two things are separated on purpose: **what the agent does** and **how it runs**.

| Resource (`api.kagent.dev/v1alpha3`) | Owns | Notable fields (from CRD schemas) |
|---|---|---|
| `AgentTemplate` | portable behaviour | `modelConfig`, `systemPrompt` / `systemPromptFrom` (ConfigMap), `promptTemplate` (Go templates with ConfigMap includes), `tools[].mcp` (server ref, tool allowlist, `requireApproval`), `tools[].subAgent.templateRef`, `skills[]` and `plugins[]` from digest-pinned git commit / OCI / bucket, `outputSchema` / `outputSchemaFrom` / `outputSchemaStrict` |
| `Harness` | runtime | exactly one of `kagent` (Go/Python ADK, with `compaction` and `memory`), `claude`, `codex`, `byo` (image implementing the private A2A contract); `workload` image override (digest-pinned), `env`, `substrate.workerPoolRef`, `substrate.snapshotPolicy` |
| `Agent` | pairing | `template.inline` or `template.ref` plus `harnessRef`, `egressPolicyRefs`; status reports compilation and readiness |
| `SandboxTemplate` | standalone sandboxes | tools image, env, egress, Substrate placement; sandboxes are created over gRPC or MCP with a TTL |
| `EgressPolicy` | network | additional HTTP(S) origins and gateway-injected credentials |
| `ModelConfig`, `ModelProviderConfig`, `RemoteMCPServer` | shared config | providers: OpenAI, Azure OpenAI, Anthropic, Vertex, Ollama, custom OpenAI-compatible endpoints; `stream: false` for gateways that do not stream |

Compilation is explicit: the translator resolves the template tree (detects cycles), a registered harness compiler emits an immutable **revision**, the controller applies it as a Substrate `ActorTemplate` with a golden snapshot. `Session` is **not** a CRD: it is PostgreSQL state exposed by gRPC, pins one revision, names one actor, and its id is the public A2A context id. A2A owns task history (append-only events, replayable into task views). Checkpoints are named boundaries matching a Substrate snapshot; forks create new sessions from a checkpoint.

Harness choices matter for Forjate: the **Claude harness** runs Claude Code as the agent runtime (the same shape as AX's Claude Code runner, but with typed outputs and HITL), **Codex** likewise, **kagent** is the in-house Go/Python ADK, and **BYO** is any image speaking the private A2A contract (the community `byo-ext` repo has no implementations yet).

## 2. What it gives an agent step

- **Invocation:** A2A `message/send` and streaming; tasks are durable, resumable, and continue after restarts.
- **Typed result:** `outputSchema` constrains the root agent's terminal output; structured output travels in the A2A task. This is the gap that made AX awkward (no exit status, no outputs).
- **Human in the loop:** extension `https://kagent.dev/extensions/hitl/v1`. The agent emits `input-required` with a `tool_approval_request` or `ask_user_request`; the gateway persists the event and quiesces the actor at that boundary; the client answers on the same task; the runtime resumes the stored continuation. Nested requests propagate from subagents. `requireApproval: true` per MCP binding makes approvals declarative.
- **Cost:** a token-usage A2A extension (`go/api/a2a/usage.go`), OTel tracing with a documented telemetry contract.
- **Isolation:** every agent is a Substrate actor with default-deny egress; model, MCP and telemetry endpoints must be DNS names covered by an `EgressPolicy` (literal IPs unsupported in Substrate rc1).
- **Lifecycle contract for callers:** documented client retry rules (request ids, idempotent Create/Fork/Delete, gRPC status table). This reads like it was written for an orchestrator to call it, which is what a Temporal activity would do.
- **Event triggers:** khook turns Kubernetes events (OOMKill, probe failures, node not ready) into agent tasks over A2A, with deduplication. Useful as a *trigger source* for harness runs, not as orchestration.

## 3. What it does not do

- No workflow graph, no step dependencies, no retries-per-step policy, no fan-out, no timers between agents. "Workflow" appears in the docs only for internal reentrant lifecycle code. Multi-agent composition is **in-process shared subagents** chosen by the parent model, or **remote A2A tool calls** from the ADKs. "Dedicated" subagents with their own harness and policy-enforced cross-session delegation are explicitly deferred.
- No authoring UI for flows. The UI is chat and resource management (React, antd, mermaid rendering), no canvas.
- No definition format portable to other executors; the CRDs are kagent's.
- 1.0 is a release candidate as of today; the `v0.10.x` Deployment-based runtime that did not need Substrate is the one documented widely on the web and is on its way out.

## 4. kagent versus AX, for the same slot

| Criterion | kagent 1.0 | Google AX 0.3 |
|---|---|---|
| Governance | CNCF Sandbox, applying for incubation; Solo.io-dominated maintainers | Google org, no foundation |
| Unit of execution | long-lived **Agent** with sessions, checkpoints, forks | one-shot **Task** (container + command), suspend/resume |
| Definition | 8 CRDs, behaviour and runtime separated, templates reusable | 3 resources, free-form `config` interpreted by the runner |
| Invocation API | A2A (standard), gRPC, MCP | own gRPC `CreateTask`, poll `GetTask` |
| Typed outputs | `outputSchema`, structured A2A output | none; read `/workspace` over ssh |
| Human gates | A2A HITL extension, `requireApproval` per tool | none (roadmap) |
| Cost / usage | token usage extension, OTel contract | none (roadmap) |
| Coding-agent runtimes | Claude and Codex harnesses, BYO contract | Claude Code runner, embeddable Go runner package |
| Workspace / repo wiring | skills and plugins from git/OCI/bucket; sandboxes for file and command work | `Workspace`: git clones, files, MCP servers, skills at a path |
| Install | Helm charts, CLI installer that also installs Substrate and PostgreSQL | plain manifests, `make deploy`, Substrate installed separately |
| UI | yes (chat, agents, sessions) | no |
| Multi-agent | in-process subagents, remote A2A tools | agent spawns Tasks itself |
| Maturity signal | rc1 on 2026-10-30, breaking from 0.10 | v0.3.1, "major breaking changes" warning |
| Shared risk | both require Agent Substrate: gVisor or microVM nodes, object store, SPIFFE, egress gateway, PostgreSQL | same |

AX's `Workspace` is the one concept kagent does not have as cleanly: kagent materialises skills and plugins from immutable artifacts and offers sandboxes, but "clone these repos at these branches before the agent starts" is AX's primitive. Everything else that an orchestrated agent step needs, kagent has and AX does not.

## 5. Fit against the harness requirements

| Requirement | kagent | Comment |
|---|---|---|
| Deterministic workflows | No | Not its job; needs Temporal/Dapr/Conductor above |
| UI separated from execution | Partly | Its UI is separable (own deployment) but is chat/admin, not a flow builder |
| Declarative YAML definition | Yes, for agents | GitOps-friendly CRDs; the *flow* still lives elsewhere |
| Portable to Temporal / Elsa / GitHub Actions | N/A | It is an executor; the harness IR would *bind* a node to an `Agent` |
| AI builder iterates the graph first | N/A | Nothing to iterate inside kagent; a node binding is `agentRef` + input mapping |
| Apache-2.0 / MIT | Yes | |
| Foundation governance | **Yes** | CNCF Sandbox; only foundation-backed agent runtime surveyed |
| Kubernetes-native, Go | Yes | controller-runtime CRDs, Helm, Go ADK |
| Human gates, outputs, cost | Yes | the three things the harness would otherwise have to add around AX |
| Homelab feasibility | Costly | Substrate requirement identical to AX; `v0.10.x` runs on plain Deployments but is legacy |

## 6. How it would plug into the layering

```
UI / builder                 unchanged
IR (Open Workflow profile)   node kind "agent" with binding: { executor: kagent, agentRef, inputSchema->A2A message, outputSchema }
Compiler -> Temporal         node -> activity RunAgentTask
Temporal activity            A2A message/send (request id = workflow id + node id) -> stream events
                             input-required (HITL) -> complete activity with "awaiting approval" -> Workflow waits on Signal
                             Signal -> new activity sends the tool_approval_response on the same A2A task
                             terminal -> structured output validated against the node's outputSchema
kagent                       Agent / AgentTemplate / Harness(claude|kagent|byo) / ModelConfig(LiteLLM) / RemoteMCPServer
Agent Substrate              actors, egress policies, snapshots to MinIO (S3)
```

Mapping notes:

- The A2A `input-required` state is the natural join between kagent's HITL and Temporal's signals; neither side needs a custom protocol, and the approval UI can be the harness UI, kagent's UI, or both.
- `ModelConfig` with a custom OpenAI-compatible endpoint lets every agent go through Forjate's LiteLLM; `RemoteMCPServer` points at the cluster's MCP servers (kmcp can manage them).
- Forjate's `agentic-reference-architecture.md` layer 4 ("domain agents that each own one capability, an orchestrator that coordinates") maps to `AgentTemplate` per capability and the workflow engine as orchestrator. kagent's deferral of "dedicated subagents with policy-enforced delegation" is precisely the piece a deterministic workflow supplies instead.
- A Forjate component `agents/kagent` would be a Helm-rendered component (use `valuesInline`, not patches) plus a Substrate component; both are new catalog entries.

## 7. Risks

- **Vendor concentration behind a foundation badge.** Solo.io writes most of the code and sells the enterprise layer; the HITL controls and AgentOps dashboard in Solo Enterprise overlap with what a harness UI would show. Watch whether features land upstream or enterprise-first. The incubation review, if it passes, is the signal that diversification is real.
- **Transition risk.** 1.0 rc1 today; anything learned from 0.10 tutorials is obsolete. Wait for GA and at least one patch release before building on the CRDs.
- **Substrate.** Same operational bill as AX: sandboxed nodes, two control planes, object store, strict egress. For a homelab harness this is the dominant cost, and kagent 1.0 offers no non-Substrate mode.
- **a2a-go licence** shows NOASSERTION on GitHub; verify before depending on it directly (the Go ADK vendors the upstream `a2aproject/a2a-go`, which is Apache-2.0).

## 8. Recommendation

1. **Prefer kagent over AX** as the future agent-step executor: it passes the governance filter, has typed outputs and HITL today, speaks A2A, and ships Helm charts and a UI.
2. **Do not block the harness on it.** Keep the executor pluggable (Kubernetes Job / Crucible first), and write the `agent` node binding so that `agentRef` + A2A is one implementation among several.
3. **Adopt two kagent conventions now, in the IR:** typed node outputs as JSON Schema (its `outputSchema`), and HITL modelled as a pause-and-resume on the *same* task rather than a separate approval entity. Both carry over to Temporal without kagent being present.
4. **Re-evaluate at kagent 1.0 GA**: install on a Substrate-capable node of the homelab, run one `Agent` with the Claude harness through LiteLLM, drive it from a Temporal activity, and measure the HITL round trip. That spike decides whether kagent plus Substrate become Forjate components.

## Sources

- https://github.com/kagent-dev/kagent (README, docs/architecture/README.md, configuration-and-compilation.md, runtime-and-lifecycle.md, persistence-checkpoints-and-forks.md, human-in-the-loop.md, a2a-subagents.md, installation.md, docs/lifecycle-retries.md, helm/kagent-crds/templates/*.yaml, go/api/a2a/hitl.go, helm/kagent/values.yaml, ui/package.json; clone at 12aa4d4, 2026-10-30)
- https://github.com/kagent-dev/kagent/releases (v1.0.0-rc1 2026-10-30, v0.10.4 2026-10-21)
- https://github.com/kagent-dev/community/blob/main/MAINTAINERS.md
- https://kagent.dev/blog/the-future-of-kagent (move to Agent Substrate, breaking changes, August 2026)
- https://www.cncf.io/projects/kagent/ (Sandbox, accepted 2025-05-22)
- https://www.cncf.io/blog/2026/10/26/isolation-security-scale/ (kagent 1.0 on Substrate)
- https://www.solo.io/blog/kagent-enterprise (Solo Enterprise for kagent, 2025-09-15)
- https://www.solo.io/blog/bringing-agentic-ai-to-kubernetes-contributing-kagent-to-cncf
- https://github.com/kagent-dev/khook, https://github.com/kagent-dev/kmcp, https://github.com/kagent-dev/byo-ext
- GitHub API, 2026-10-30: licence, stars, created_at, releases, org repositories

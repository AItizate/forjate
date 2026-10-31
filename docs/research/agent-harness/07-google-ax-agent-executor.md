---
title: "Google AX (Agent Executor) and Agent Substrate: what they are and where they fit"
date: 2026-10-30
status: research
sources_verified: true
verification_method: "Shallow clones of google/ax (HEAD f0228f1, 2026-10-30) and agent-substrate/substrate (HEAD 659832f5, 2026-10-31) read directly; GitHub API for licence, stars, releases and contributors; Google Cloud announcement blog; CNCF sandbox issues."
---

# Google AX (Agent Executor) and Agent Substrate

This corrects the earlier assumption in [04](04-agent-frameworks-deterministic-workflows.md) that "Google AX" meant ADK, Genkit or ax-llm/ax. It is a fourth, distinct project: **github.com/google/ax, "Agent Executor"**, a Kubernetes runtime for sandboxed agent tasks, announced on 2026-05-20 together with **Agent Substrate**, the sandboxing layer it requires.

## TL;DR

- **AX is a sandboxed-task runtime, not a workflow engine.** Its own docs say so: "An agent is not one process that runs to completion; over its lifetime it plans, delegates, retries, and fans work out. **AX does not try to model that shape.**" It has no DAG, no steps, no dependencies between tasks, no retries, no human gates, no timers. The deterministic-workflow layer Sebas wants is exactly what AX leaves to the caller.
- **Where it fits in the harness layering: the node runtime for agent steps.** A Temporal activity (or any orchestrator) creates an AX `Task`, waits for `Ready`, and reads the result from the workspace. AX replaces "run Claude Code in a pod with a cloned repo and MCP servers", which is otherwise hand-built. It complements Temporal and the Open Workflow IR; it does not compete with them.
- **Governance splits in two.** Agent Substrate (the required dependency) was accepted as a **CNCF Sandbox** project in October 2026 (TOC vote 2026-09-29), Apache-2.0. AX itself lives under the `google` GitHub org, Apache-2.0, Google-staffed (27 of 50 commits since May 2026 from google.com addresses, lead author Jaana Dogan), no foundation, with a README warning of "major breaking changes prior to a stable release".
- **Operational weight is high.** Substrate refuses plain containers: every actor runs under gVisor `runsc` or a Kata + Cloud Hypervisor microVM, with SPIFFE identity, a default-deny egress gateway, an object store for snapshots (GCS or S3, so MinIO fits) and PostgreSQL. AX adds its own PostgreSQL and gRPC server. Plain manifests, no Helm chart, images must be digest-pinned.
- **Verdict:** track it, do not build on it today. Design the harness so an "agent step" has a pluggable executor, prototype with a plain Kubernetes Job or Crucible, and add an AX executor when `v1alpha1` stabilises and the roadmap items that matter to a harness (budgets, approval policies, exit status, trajectories) land.

## Governance and licence table

| Project | Owner | Foundation | Licence | Language | Created | Latest release | Stars | Notes |
|---|---|---|---|---|---|---|---|---|
| google/ax (Agent Executor) | Google | none | Apache-2.0 | Go | 2026-03-30 | v0.3.1 (2026-09-25) | 14.4k | 84 open issues; ~12 contributors since May 2026; "heavy development" warning |
| agent-substrate/substrate | Google-originated, own org | **CNCF Sandbox** (accepted Oct 2026) | Apache-2.0 | Go | 2026-05-13 | pre-1.0 | 6.0k | GOVERNANCE.md with four role tiers, DCO sign-off, weekly public meeting, CNCF Slack channels |
| kagent (mentioned by Substrate) | kagent-dev | CNCF Sandbox | Apache-2.0 | Go | — | — | — | Kubernetes-native agent framework that uses Substrate as execution backend; not evaluated here |

## 1. What AX actually is

Three resources under `ax.io/v1alpha1`, applied with a `kubectl`-shaped CLI (`ax apply|get|describe|delete|suspend|resume|ssh`):

| Kind | What it declares | Schema highlights (from `pkg/apis/v1alpha1/ax.proto`) |
|---|---|---|
| `Task` | One sandboxed container running one agent command | `image` (digest-pinned), `command`, `env`, `resources.limits` (cpu, memory only), `workspace` ref, `debug`, free-form `config` (≤16 KiB, uninterpreted by the control plane) |
| `Workspace` | What the agent finds at `/workspace` before it starts | `git[]` (repo, branch, dir), `files[]`, `mcp.servers[]` (http endpoint or stdio command), `mcp.registries[]`, `skills.registries[]`, `skills.path` |
| `Model` | Which LLM the platform uses and where the key is | `provider` (google, anthropic), `model`, `secretKey` (Kubernetes Secret ref), `parameters` |

Status is `phase` plus two conditions, `WorkspaceReady` and `Ready`. Tasks are immutable once created. The control plane stores specs in PostgreSQL (not CRDs, by design: "millions of short-lived tasks pushes etcd past its comfort zone") and reconciles against Substrate under distributed locks. Everything that belongs to the running actor (phase, worker IP, `Ready`) is read live from Substrate, never cached.

**The runner contract** is the extensibility point. AX always starts the container as `/usr/local/bin/ax-task-runner`, passes `AX_TASK_YAML` and `AX_WORKSPACE_YAML` as environment variables, probes `/readyz` on port 80, and expects the runner to clone repos once, write MCP config, start `spec.command`, serve a loopback metadata server, and stay alive after the command exits. Three customisation levels: extend the default image, embed the Go `runner` package, or rewrite the runner in any language. A **Claude Code runner** ships in `cmd/runners/claude-code-runner`: it builds `claude --print --<flag>=...` from `spec.config` (camelCase keys map to CLI flags) and converts the Workspace's MCP servers into `--mcp-config`. Headless runs need `permissionMode: bypassPermissions` and `IS_SANDBOX=1`, which the image sets.

**Durability** is suspend/resume of the whole sandbox (memory plus `/workspace` snapshot via Substrate), not event-sourced replay. "Pick up exactly where it left off" means the process tree is checkpointed, which is a different and complementary guarantee to Temporal's.

## 2. What AX does not have (and a harness needs)

Read directly from the schema and docs on 2026-10-30:

- No workflow: no edges, no `dependsOn`, no fan-out, no conditionals. Composition is "the agent spawns more tasks" via gRPC.
- No exit status: "The control plane does not currently read the command's exit status back from the container." Results must be fetched from `/workspace` (over `ax ssh`, which requires `debug: true`) or pushed by the runner's `OnCommandExit` hook.
- No outputs or artifacts model, no retries, no timeouts, no token or cost budgets, no approval gates. All four appear in the **roadmap** ("token/timeout budgets, and approval policies" under Task; "Telemetry and Trajectory Collection"; "Stateful Task Branching").
- No events or webhooks on phase changes; callers poll `GetTask`.
- No UI. The surface is the CLI and the `ax.v1alpha1.AX` gRPC service.
- Model providers: `google` and `anthropic` only; MCP and skill registries have `provider: google` as the documented value, and registry queries "are not resolved yet".
- Spec size: the whole Task must fit in 31 KiB because it travels in one environment variable.

## 3. Agent Substrate, the real dependency

Substrate is the layer that gives AX its security story and its density claims. What a Forjate deployment would take on:

- **Sandbox runtimes:** gVisor (`runsc`, default; needs a build with `--allow-connected-on-save`) or Kata + Cloud Hypervisor microVMs. "Plain Linux containers are not supported." gVisor runs on ordinary Linux nodes; microVMs need KVM.
- **Components:** `ate-api-server`, `atelet` node supervisor, `ateworker-gvisor` or `ateworker-microvm` warm worker pools, `atenet-router` ingress, `atenet-egress` credential-injecting egress gateway, SPIFFE identity for every actor, an object-store plugin sidecar (GCS or S3) for snapshots, PostgreSQL, optional CSI plugin for external volumes with bidirectional mount propagation.
- **Install:** `go run ./cmd/ate-setup deploy ...` or a static `docs/examples/substrate-install.yaml`; there is an operator install guide. Tested path is kind and GKE.
- **Maturity:** pre-1.0, "not making any guarantees about backward compatibility"; the architecture page is marked `status: planned` ("much of this architecture is aspirational"). Google addresses author the large majority of commits.
- **Governance:** real and foundation-backed. Written GOVERNANCE.md, DCO, public weekly meeting, CNCF Slack, CNCF Sandbox onboarding tracked in agent-substrate/substrate issue 3060 and cncf/sandbox issues 523 and 542. This is the piece that passes Sebas's first filter.

## 4. Fit against the harness requirements

| Requirement | AX | Comment |
|---|---|---|
| Deterministic workflows | No | Explicitly out of scope; needs Temporal, Dapr or Conductor above it |
| UI separated from execution | N/A | No UI at all; gRPC API is clean enough to drive from anything |
| Declarative YAML definition | Partial | Tasks, Workspaces and Models are YAML; the *flow* between tasks is not |
| Portable to Temporal / Elsa / GitHub Actions | No | AX is an execution target, not a definition format |
| AI builder iterates the graph first | No | Nothing to iterate; a graph node could *bind* to an AX Task |
| Apache-2.0 / MIT | Yes | Both projects Apache-2.0 |
| Foundation governance | Half | Substrate CNCF Sandbox; AX Google-only |
| Kubernetes-native, Go | Yes | Go end to end; Postgres instead of CRDs by design |
| Sandboxed, credential-free agent execution | **Strong** | This is the thing it does better than anything else surveyed |
| Homelab feasibility | Costly | gVisor on bare metal works; two Postgres, object store, SPIFFE, egress gateway, warm worker pools |

## 5. How it would plug into the proposed layering

```
UI / builder                      unchanged
IR (Open Workflow profile)        node kind "agent" with binding: { executor: ax, image, workspace, config }
Compiler -> Temporal              node -> activity RunAXTask
Temporal activity RunAXTask       CreateTask over gRPC -> poll GetTask until Ready/Failed -> read result
                                  (runner OnCommandExit posts result to a Forjate endpoint, or activity reads /workspace via guest services)
AX control plane                  Task / Workspace / Model
Agent Substrate                   gVisor or microVM actor, SPIFFE, egress gateway, snapshots to MinIO (S3)
```

Mapping notes:

- A Forjate **use case** (the Crucible `UseCase` with `seed -> run -> verify`) and an AX **Workspace** describe the same thing from two sides: what the agent finds ready when it starts. If AX is adopted, Workspace becomes the runtime projection of a use case's contract, and Crucible's TTL semantics would sit above AX's suspend/resume.
- Temporal keeps retries, timeouts, HITL and budgets, so AX's roadmap gaps do not block the design; they only decide which layer enforces them.
- The Claude Code runner is a working reference for "intent node whose implementation is a coding agent with MCP tools", which is the most common node in Sebas's intended workflows.
- Until exit status and outputs exist in AX, the runner's `OnCommandExit` hook (level 2 customisation, Go) is the way to report results back; it costs one small custom runner image.

## 6. Risks

- **API churn.** `v1alpha1` with an explicit breaking-changes warning; the controller was still being restructured on 2026-10-30 (last commit: "replace Reconcile with explicit Suspend and Resume").
- **Google-shaped defaults.** MCP and skill registries with `provider: google`, GCS first for snapshots, GKE as the reference platform. Everything has an S3 or self-hosted path, but the happy path is Google Cloud.
- **Two control planes plus Substrate's node agents** for what a Kubernetes Job does today. Justified only when sandboxing untrusted agent code and density matter, which for an internal harness on a homelab is not yet the case.
- **Bus factor on AX** is concentrated in a handful of Google engineers; Substrate's CNCF status mitigates the layer below, not AX.

## 7. Recommendation

1. Keep AX out of the first harness iteration. Model agent steps as a node kind with a pluggable executor; ship the Kubernetes Job / Crucible executor first.
2. Reuse two AX ideas now, at the schema level: the **Workspace** shape (git, files, MCP servers, skills path) as the binding payload of an agent node, and the **runner contract** (metadata server, readiness after workspace prep, stay alive after exit) for Forjate's own agent images. Both are cheap to align with and make a later AX executor trivial.
3. Re-evaluate when AX publishes `v1beta1` or ships exit status, budgets and approval policies, or when Forjate needs to run untrusted or multi-tenant agents. Evaluate **kagent** (CNCF Sandbox, uses Substrate) at the same time; it was not covered by this research and may be the foundation-governed way to consume Substrate.

## Sources

- https://github.com/google/ax (README, DESIGN.md, docs/concepts.md, docs/manifests.md, docs/runner.md, docs/sandbox.md, docs/roadmap.md, examples/claude-code/README.md, pkg/apis/v1alpha1/ax.proto; clone at f0228f1, 2026-10-30)
- https://github.com/google/ax/releases (v0.3.1, 2026-09-25)
- https://cloud.google.com/blog/products/ai-machine-learning/agent-executor-googles-distributed-agent-runtime (announcement, 2026-05-20)
- https://agentexecutor.io
- https://github.com/agent-substrate/substrate (README, GOVERNANCE.md, docs/concepts/architecture.md, docs/guides; clone at 659832f5, 2026-10-31)
- https://www.cncf.io/projects/agent-substrate/
- https://github.com/cncf/sandbox/issues/523 and https://github.com/cncf/sandbox/issues/542 (Sandbox application and onboarding)
- https://github.com/agent-substrate/substrate/issues/3060 (CNCF onboarding tracking)
- https://github.com/kagent-dev/kagent
- GitHub API, 2026-10-30: licence, stars, created_at, releases, contributors for both repos

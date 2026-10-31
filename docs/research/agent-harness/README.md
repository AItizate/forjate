---
title: Agent harness research
date: 2026-10-30
status: research
---

# Agent harness on Forjate — research index

Working notes toward an **agent harness**: a system that runs agent tasks automatically through **deterministic workflows**, with the authoring UI decoupled from the execution engine. This folder holds one research document per axis; the cross-reading, disagreements and open decisions live in [00-synthesis.md](00-synthesis.md).

## The problem statement

- Agent runs must be **deterministic workflows**: explicit steps, retries, timeouts, human gates, durable state; the LLM call is a step inside the graph, not the control loop.
- The **UI is separate from execution**. Its job is to iterate fast, with AI, on the *graph* (nodes, edges, intent per node). Only after the flow settles does the inner *wiring* begin (activities, actions, MCP tools, code per step).
- The definition is **declarative** (YAML/JSON) and must be portable: the same graph should be postable to Temporal (through a DSL interpreter), Elsa Workflows, a GitHub-Actions-shaped executor, or others.
- Candidate definition formats: the GitHub Actions workflow schema (so existing actions become harness steps), a Temporal-style DSL, CNCF Serverless Workflow, Conductor JSON, or a custom schema.
- Filters, in this order: **governance** (foundation-backed over single vendor), **licence** (Apache-2.0 / MIT only), then Kubernetes-native deployment and Go tooling.

## Documents

| # | Document | Question it answers |
|---|----------|---------------------|
| 00 | [Synthesis and decision points](00-synthesis.md) | What do the six axes agree on, where do they disagree, and what must Sebas decide? |
| 01 | [Temporal as agent harness](01-temporal-as-agent-harness.md) | Can Temporal be the execution engine? What DSL layer, agent tooling and UI gaps exist? |
| 02 | [GitHub Actions schema as agent DSL](02-github-actions-schema-as-agent-dsl.md) | Can the GitHub Actions YAML schema be the workflow DSL, and what already executes it outside GitHub? |
| 03 | [Durable workflow engines, OSS landscape](03-durable-workflow-engines-oss-landscape.md) | Which permissive, foundation-backed engines compete with Temporal? DSL-first vs code-first. |
| 04 | [Agent frameworks with deterministic workflows](04-agent-frameworks-deterministic-workflows.md) | Which agent SDKs (Google ADK/Genkit, ax, LangGraph, MS Agent Framework, Dapr Agents...) give graph primitives and serialisable definitions? |
| 05 | [AI-assisted workflow builders and UI](05-ai-assisted-workflow-builders-ui.md) | What OSS builders generate graphs with AI, and what blocks exist to build a custom one? |
| 06 | [Portable workflow DSL and interchange](06-portable-workflow-dsl-and-interchange.md) | Which declarative format should be the canonical IR, and how does it compile to each executor? |
| 07 | [Google AX (Agent Executor) and Agent Substrate](07-google-ax-agent-executor.md) | What google/ax really is (a sandboxed-task runtime, not a workflow engine), and where it fits in the layering. |
| 08 | [kagent](08-kagent.md) | The CNCF agent control plane on Substrate: agents as CRDs, A2A, HITL, typed outputs. Compared with AX for the agent-step slot. |

## How these relate to Forjate today

- `k8s/components/workflows/temporal` and `k8s/components/bundles/temporal-stack` already ship Temporal + PostgreSQL.
- `docs/agentic-reference-architecture.md` places a *durable workflow engine* at layer 3 ("planning and orchestration") and names an evaluation harness as catalog backlog.
- `docs/use-case-builder/` is the existing AI-assisted *planner*; the harness is the *runtime* counterpart.
- `crucible` (sibling repo) is the operator that turns ephemeral use cases into a CRD; a harness run could be a Crucible use case with a short TTL.

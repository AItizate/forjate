---
title: "The 'engineering software factory' pattern: dsh-superagent, DeepSeek Harness, Herdr and OSC 7501"
date: 2026-11-05
status: research
sources_verified: true
verification_method: "Shallow clones read directly: deepseek-ai/dsh-superagent-prototype (8c32a9d, 2026-10-31; docs 000-007), deepseek-ai/deepseek-harness (fcc0ad46, 2026-11-04; docs/architecture.md, agent-lifecycle.md, session-format-status.md, packages/*/README.md); GitHub API for licences, stars, releases; herdr.dev docs; Mitchell Hashimoto's OSC 7501 post."
---

# The "engineering software factory" pattern

Trigger for this document: a LinkedIn post describing software engineering in 2027 as "you write a feature on GitHub / Azure DevOps / GitLab; the engineering software factory swallows it whole; durable agents clock in; they grab tools, follow rules, run **your** inferencing models; they hand back evidence, traces and artifacts", and the same author's praise of DeepSeek Harness (DSH), its `dsh-superagent` bundle, and Herdr with OSC 7501. Sebas's intuition that "this points the same way" as the harness is right. This page says exactly how, piece by piece, and what to take from each.

## TL;DR

- **The five-step post is the harness layering in prose.** Step 1 is the intake (SCM as trigger source), step 2 the deterministic control loop, step 3 durable agent steps, step 4 tools over MCP plus the model gateway, step 5 outputs, traces and artifacts. Nothing in the post needs a new layer; the research already covers each one.
- **dsh-superagent is the best-articulated *control loop* for this pattern seen in this research.** Its domain model (Source → Trigger → Thread → Eval → Mandate → Ticket → Assignment → Executor → Report → Channel) and its ticket stages (working, queued, idle, awaiting answer, awaiting review, blocked, failed) are exactly the vocabulary a harness needs for "agents clock in from GitHub and hand back a PR". It is a research prototype, MIT, in-process TypeScript, SQLite, single machine, bound to DSH as executor. Take the model, not the code.
- **DeepSeek Harness is a plausible agent-step runtime, not a workflow engine.** MIT, Node/TypeScript, everything-is-a-plugin kernel (Cordis), profiles `web`, `headless`, `sdk`, `acp`, an **append-only session journal** whose rule "model-visible means logged" is the strongest evidence story surveyed, goal rounds ("Ralph loops"), team task boards, jobs, RFC 5545 schedules, same-world sandbox. Its `workflow` tool runs **model-authored** orchestration scripts, which is the opposite of a deterministic workflow. Developer preview, breaking changes announced.
- **Herdr and OSC 7501 are the human-side half: the "needs-you" inbox.** Herdr (Apache-2.0, Rust, 48k stars, small company) multiplexes agent terminals and rolls them up to working / blocked / done / idle, with a socket API where agents wait on each other's state. OSC 7501 (Mitchell Hashimoto, 2026-10-06, spec under Rex) is a dozen-line escape sequence that lets any program report `idle | working | blocked(kind=permission|question|auth) | done | error`. That state vocabulary is the thing to standardise on across the harness.
- **Governance:** all three are vendor- or individual-owned (DeepSeek, herdrdev, one maintainer for the spec). Licences are clean (MIT, Apache-2.0). None passes the foundation filter, so they are pattern sources and optional executors, not the spine.

## Governance and licence table

| Project | Owner | Foundation | Licence | Language | Created | Latest release | Stars | Status |
|---|---|---|---|---|---|---|---|---|
| deepseek-ai/deepseek-harness (DSH) | DeepSeek | none | MIT | TypeScript / Node (+Python SDK) | 2026-08-13 | dsh-v0.2.2-rc.1 (2026-11-04) | 273.9k | "developer preview… THERE WILL BE COMPATIBILITY-BREAKING CHANGES" |
| deepseek-ai/dsh-superagent-prototype | DeepSeek Harness team | none | MIT | TypeScript | 2026-10-31 | none (single commit + fixes) | 19.5k | "Research prototype for reference only, not an official DeepSeek product" |
| herdrdev/herdr | herdrdev (company; sponsors, "enterprise / partnership" contact) | none | Apache-2.0 | Rust | 2026-03-27 | rolling | 48.3k | stable releases, Homebrew formula; herdr-app (desktop) and herdr-core also Apache-2.0 |
| OSC 7501 "program status" | Mitchell Hashimoto (Ghostty); spec hosted under superlogical.com/rex | none | open spec, rev 0.4 | — | 2026-10-06 | — | — | implemented by Ghostty, Rex, Herdr, dsh-tui, Keepstate; PoCs in Claude Code, Codex, Terraform |
| cordiverse/cordis (DSH kernel) | independent | none | MIT (per DSH THIRD_PARTY_NOTICES) | TypeScript | — | — | — | paper arXiv 2608.25512 |

## 1. The post, mapped

| Post | What it means | Where the research already places it |
|---|---|---|
| "You write a feature on GitHub / Azure DevOps / GitLab" | SCM is the intake. Issues, PR comments, labels, CI results and chat mentions are *triggers*, not prompts | dsh-superagent `Source`/`Trigger`; GitHub Agentic Workflows ([02](02-github-actions-schema-as-agent-dsl.md)); khook for cluster events ([08](08-kagent.md)) |
| "The engineering software factory swallows it whole" | A control loop decides whether a trigger is work, under whose authority, and opens a unit of work with a scope | dsh-superagent `Eval` → `Mandate` → `Ticket`; the deterministic workflow layer (Temporal + Open Workflow IR, [01](01-temporal-as-agent-harness.md), [06](06-portable-workflow-dsl-and-interchange.md)) |
| "Durable agents clock in. No small talk with the human" | Agent steps are durable, resumable, and speak only when a person must act | AX / kagent / DSH headless as executors ([07](07-google-ax-agent-executor.md), [08](08-kagent.md), this page); dsh-superagent's philosophy "speaks only when a person must act or can use a result" |
| "They grab tools, follow rules, run YOUR inferencing models" | MCP tools, written policy (allowlists, admission rules, blocked commands), self-hosted or gateway-routed models | MCP + LiteLLM in every layering; dsh-superagent `Policy` with versioned rules; kagent `EgressPolicy` and `requireApproval` |
| "They hand back evidence, traces and artifacts" | Typed outputs, an append-only journal, OTel traces, PRs and files as deliverables | kagent `outputSchema`; DSH session journal and `deliverables`; OTel GenAI; AX/kagent roadmap "trajectories" |

Conclusion: the post describes the harness. What it adds is *emphasis*: intake from SCM as a first-class layer, and attention economics ("take as little human attention as possible") as a design rule for the UI.

## 2. dsh-superagent: the control loop, read closely

A proactive coding agent for **one GitHub repository**, packaged as a DSH bundle, listening to GitHub and optionally Feishu. Docs 000 to 008 are unusually precise; the domain model is the asset.

**Flow.** A `Source` (GitHub, Feishu) produces `Triggers`, each belonging to `Threads` (an issue, a PR, a chat). Triggers fan out as context to the `Tickets` subscribed to their threads; everything else enters `Eval`, where the **main Session** (an LLM with a router preset) decides accept / stop / ignore / unavailable under a `Policy` gate. Accept creates a `Ticket` with a `Mandate` (who asked, under which rule, `via` addressed | followup | admission | bot), `Subscriptions`, and a first `Assignment`. The `Executor` runs the ticket in its own DSH session `worker-<ticket>` and its own directory (typically a `git worktree`), prepared by a configurable command. Results go back to the originating conversation through a `Channel` as acknowledgement, answer, result or attention message.

**Reports and stages.** A worker reports `progress | waiting | ready | blocked | failed | dropped`. The engine derives one stage per ticket, first match wins: *Input undelivered*, *Awaiting answer*, *Awaiting review* (ready with a PR), *Blocked / Failed*, *Queued*, *Waiting for a Trigger* (idle), *Working*. "Person" stages free the worker slot immediately; a human message releases a blocked ticket. The panel "shows only what needs a person".

**Mechanics worth copying.**
- Concurrency as **worker slots** with one spare slot reserved for a person's message, so new work never blocks a human continuing existing work.
- Transient model/network failures (408, 429, 5xx, reset) retried three times with growing backoff; a failed prepare command is not retried automatically.
- **Recovery after restart:** interrupted assignments restart with a recovery note and the inputs the session had not taken; input "read" is defined precisely (taken into history and followed by a report or turn end).
- Background jobs capped at 30 minutes per turn; a dev server offered for review may outlive the turn without holding a slot.
- Ticket end is driven by **thread closes** (PR merged or closed), not by the agent saying "done"; a `ready` report without a PR completes the ticket.
- Policy is **versioned and hashed**; changing a rule notifies exactly the open tickets it bears on and restarts in-flight evals. Outside auto mode, proactive accepts become "would accept" records (dry-run of autonomy).
- Auto-merge is governed by a prompt and GitHub branch protection, never by host logic; the agent withdraws auto-merge before pushing a new revision.

**What it is not.** The `Engine` is an in-process TypeScript state machine over SQLite, with a directory lock to prevent a second process; workers run as the operator's OS user; the docs state that wrappers "establish defaults, not a security boundary". There is no durable workflow engine, no multi-node, no graph of steps: within a ticket the agent is free-form. Eval is itself an LLM judgement (the "main Session"), gated by deterministic policy. It is a **reference design**, published as such.

## 3. DeepSeek Harness: the agent runtime underneath

**Shape.** A Cordis plugin tree composed at boot from ordered layers: a *profile* (`web`, `headless`, `sdk`, `sdk-minimal`, `acp`) stacks *bundles* (`dsh-base` = model adapters, tools, persistence, sandbox and approval policy, settings, credentials, telemetry) plus `cordis.patch.yml` overlays. The model adapter, tool registry, session log and **the agent loop itself** are replaceable plugins. Model-agnostic over OpenAI-compatible endpoints, so LiteLLM fits.

**Journal.** `core/session` is an append-only `SessionEvent` log (JSONL, zstd, versioned formats with adjacent migrations, format v4 released at dsh-v0.2.0-rc.2). Rule: **"Model-visible means logged. Every model request must be reconstructable from the log."** Turn and step boundaries, system/user/assistant messages, tool calls and results are durable events; fork, resume, transcripts and telemetry derive from them. This is the "evidence and traces" of the post, implemented. OSC 7501 reporting of the session state is done by the `dsh-tui` plugin.

**Primitives relevant to a harness, and their nature.**

| Package group | What it does | Deterministic? |
|---|---|---|
| `goal` + `goal-round-driver` | one durable completion objective per session; automatic continuation in sequential **Rounds** (the "Ralph loop": a fresh agent each round until the goal is met; the fixed loop lives in `experimental/tool-ralph`) | the loop is; the content of each round is not |
| `team` | shared task board with ownership and dependencies for a subagent tree | board is explicit; assignment is model-driven |
| `jobs` | background jobs owned by the session, waited on and cancelled without blocking the turn | yes |
| `schedule` | RFC 5545 recurring tasks delivered as follow-up messages to a session | yes |
| `workflow` | the model **writes an orchestration script** that fans out subagents and returns a value, run in a sandboxed Node runtime | **no**: model-authored at run time |
| `sandbox` | file-effect confinement (read-only / workspace-write / full) via bwrap + Landlock, Seatbelt, Windows restricted token; same kernel | n/a |
| `deliverables` | `present` tool declares final files; per-turn changed-files summaries from git snapshots | yes |
| `acp` | automation-only server profile; `headless` is a one-shot runner | n/a |

**Reading for the harness.** DSH is a strong candidate for *what runs inside an agent node*: `headless` or `acp` in a container, journal exported as the node's trace, `present` as the artifact declaration, LiteLLM as the model. It is not a candidate for the deterministic control loop: its workflow construct is generated by the model, and its multi-agent features coordinate through prompts and boards, not through a declared graph. Risks: vendor-owned, pre-1.0 with announced breaking changes, Node runtime, and a very large surface (dozens of package groups) for a step executor.

## 4. Herdr and OSC 7501: the operator side

**Herdr** owns agents' terminals: each coding agent gets a PTY pane in a background server (detach, SSH, several machines in one window), and a sidebar rolls every pane up to working / blocked / done / idle. A **socket API** lets agents orchestrate agents: `agent.prompt` submits input and can start a wait atomically; `agent.wait` blocks until a target *semantic* state ("Agent waits observe semantic state, not arbitrary command execution"); `pane.report_agent` lets integrations report state; lifecycle subscriptions replace polling. It wraps nothing; agents keep their own UX.

**OSC 7501** is the protocol that removes the heuristics Herdr used to need (it had "16 Claude Code detection rules"). Format: `ESC ] 7501 ; key=value:key=value ESC \` with `state` required (`idle | working | done | blocked | error`), optional `app`, `msg` (base64), `kind` for blocked (`permission | question | auth`), `progress` for working. Implementations are a dozen lines. Herdr, dsh-tui, Ghostty, Rex and Keepstate already speak it.

**Reading for the harness.** Two takeaways, neither requiring Herdr itself:

1. **One state vocabulary.** The research now has four: OSC 7501's five states; dsh-superagent's six reports and seven stages; kagent's A2A `working | input-required | completed | failed` plus HITL `tool_approval | ask_user`; AX's `Running | Suspended | Failed`. They align almost perfectly. The harness node state should be the OSC 7501 set with `blocked.kind` from `{permission, question, auth, review}` (review is dsh-superagent's "awaiting review", missing from 7501). Runners emit it over the PTY for terminal operators; the control plane carries it over AG-UI for the web panel; Temporal keeps it as workflow search attributes.
2. **The inbox is the UI, not the chat.** Both Herdr's sidebar and dsh-superagent's panel converge on a list of work items sorted by *whether a human is needed*, with the agent's transcript one click away. This should be the operations view of the harness UI, next to the graph builder, and it is what the post means by "no small talk".

## 5. What to take, and from where

| Need in the harness | Take from | Why |
|---|---|---|
| Intake and authority model (who may start work, under which rule, what the agent may touch) | dsh-superagent `Source / Trigger / Thread / Eval / Mandate / Policy`, including `via` bases and versioned policy with "would accept" dry runs | the only fully specified design of SCM-driven intake with autonomy staged by policy; matches Forjate's crawl / walk / run gates |
| Unit of work and its lifecycle | dsh-superagent `Ticket / Assignment / Report`, thread-close-driven completion, worker slots with a human spare | precise, tested in daily use by its authors, and directly expressible as a Temporal workflow with child workflows and signals |
| Node state vocabulary and operator inbox | OSC 7501 states + `blocked.kind`; Herdr's sidebar semantics and `agent.wait` | de facto standard across terminals and agents; cheap to emit; maps to kagent HITL and Temporal signals |
| Evidence | DSH journal rule "model-visible means logged"; `deliverables`; OTel GenAI attributes | reconstructable requests are the audit trail layer 6 of the reference architecture asks for |
| Agent-step runtime (pluggable) | Kubernetes Job or Crucible first; then kagent (preferred), DSH `headless`/`acp` in a container, or AX | see [07](07-google-ax-agent-executor.md) and [08](08-kagent.md); DSH adds a journal-native option |
| Not to take | dsh-superagent's in-process SQLite engine; DSH's model-authored `workflow` tool; Herdr as a dependency | the first is single-node research code, the second is non-deterministic by design, the third is a terminal product, not a service |

## 6. How dsh-superagent's model lands on Temporal

```
Source (GitHub webhook / poll)      -> Temporal Schedule or signal-only "intake" workflow per repo
Trigger                             -> signal payload; deduplicated by Source position (idempotency key)
Thread                              -> workflow search attribute; subscriptions = signal routing table
Eval (LLM + Policy gate)            -> activity: policy.gate() deterministic, then LLM assess, then
                                       assessmentOutcome(); "would accept" recorded when not in auto mode
Ticket + Mandate                    -> one Ticket workflow per accepted trigger; Mandate immutable in workflow state
Assignment                          -> child workflow running the Open Workflow IR of the chosen use case;
                                       agent nodes bound to an executor (Job / kagent / DSH headless / AX)
Report (progress|waiting|ready|...) -> Update from the executor; stage derived deterministically in workflow code
Person stages                       -> workflow waits on a Signal; OSC 7501 / AG-UI state = blocked(kind)
Thread close (PR merged/closed)     -> signal; ticket completes per the followsDone rule
Channel replies                     -> activities with an outbox (receipt + retry), as in src/app/outbox.ts
Policy change                       -> signal to the tickets it bears on; evals in flight restarted
```

The gain over the prototype: multi-node durability, replay-tested lifecycle, retries and timers owned by the engine, and executors swappable per node. The loss: nothing the prototype has, since its engine is already event-shaped (`DomainEvents`: `trigger.received`, `eval.started`, `decision.recorded`, `ticket.created`, …).

## 7. Risks and open points

- **DSH churn and size.** A pre-1.0 Node runtime with announced breaking changes and a session-format migration chain is a heavy executor to pin; prefer running it inside a digest-pinned image behind the executor interface.
- **dsh-superagent's Eval is an LLM.** Deterministic policy gates it, but the accept decision is model-made. Forjate's autonomy stages ([agentic-reference-architecture](../agentic-reference-architecture.md)) say to start with "would accept" records only, which the prototype supports natively.
- **OSC 7501 is rev 0.4 and one person's spec.** Cheap enough to adopt anyway; keep the harness vocabulary as its own JSON Schema with a 7501 projection.
- **Herdr's company model** (sponsors, enterprise contact) is fine for a desktop tool; do not build a service dependency on it.
- Not verified here: Cordis's licence and governance beyond DSH's third-party notices; the exact OSC 7501 spec text at its canonical URL; DSH `acp` profile's suitability as a long-running server inside Kubernetes.

## Sources

- https://github.com/deepseek-ai/dsh-superagent-prototype (README, docs/000-philosophy.md, 001-domain.md, 002-authorization.md, 003-execution.md, 007-architecture.md; clone 8c32a9d, 2026-10-31)
- https://github.com/deepseek-ai/deepseek-harness (README, docs/architecture.md, docs/agent-lifecycle.md, docs/session-format-status.md, packages/{workflow,goal,jobs,schedule,team,deliverables,sandbox}/README.md; clone fcc0ad46, 2026-11-04)
- https://www.deepseek.com/en/harness/ (official plugin list, public preview)
- DeepSeek, "Exploring Super-agent Design: Towards a More Autonomous Agent System", 2026-10-31 (secondary coverage; the prototype README says it does not match the paper's internal version)
- https://github.com/herdrdev/herdr and https://herdr.dev/docs/socket-api/
- https://mitchellh.com/writing/program-status-osc7501 (2026-10-06); spec: https://www.superlogical.com/rex/docs/build/program-status
- https://github.com/ccch1mneyyy/dsh-TUI/pull/1561 (dsh-tui reports OSC 7501), https://github.com/herdrdev/herdr/pull/5172 (Herdr OSC 7501)
- GitHub API, 2026-11-05: licences, stars, created_at, releases for the repositories above

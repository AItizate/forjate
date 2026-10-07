# Use-Case Builder — execution plan

> An agentic team that takes a one-paragraph business problem and turns it into a Forjate overlay, staged Crawl → Walk → Run, with structured, reviewable artifacts at every step.

Status: **Phase 3 done (tag `builder-p3`, 2026-10-03)** · Owner: Sebas · Created: 2026-10-02

---

## 1. What we are building

A **coordinator** skill guides the user from "I want to automate X" to a deployable use case. It calls a **stage planner** (Crawl / Walk / Run, mapped to Forjate's Lab / MVP / Production ladder in `docs/lab-to-production.md`) and a **panel of experts**, one per decision area. Every expert emits a **structured decision record** (YAML, schema-validated) that feeds the next step and ends up as a `k8s/overlays/usecases/<name>/` overlay plus its `usecase.yaml` contract, runnable by `scripts/ephemeral/ephemeral.sh`.

The seven decision areas requested:

| Area | Expert | Core question it answers per stage |
|------|--------|------------------------------------|
| Data & memory | `forjate:data-store` | Where does state live? Short-term (session/working) vs long-term (facts, embeddings, artifacts). Which catalog component, what retention. |
| Data pipeline | `forjate:data-pipeline` | How does data get in, get transformed, get out? Batch vs CDC vs event-driven. Seed strategy for the ephemeral env. |
| Security | `forjate:security` | Secrets mechanism, auth surface, network isolation, PSA level, data classification, audit. Written for corporate / regulated environments. |
| Architecture & integration | `forjate:architecture` | Topology, which systems to integrate, API surface (apification), sync vs durable (Temporal), messaging. |
| UX | `forjate:ux` | What is the right surface for the stage: CLI, chat channel, Open WebUI, custom web, API-only. Human-in-the-loop points. |
| Quality | `forjate:quality` | Quality gates per stage transition, what the `verify` Job proves, test pyramid for the agent, eval strategy for LLM behavior. |
| DevOps & delivery | `forjate:devops` | Local vs k3d vs cluster, GitOps (ArgoCD), CI gates, image pipeline, observability baseline, rollback. |
| Business & process | `forjate:business` | Why are we doing this? Value hypothesis, success KPI per stage, cost per stage, actors, systems of record, as-is process with exceptions and SLAs, go/no-go. Produces the numbers the quality gates measure. |
| AI engineering | `forjate:ai-engineering` | Model choice (local vs API, size, cost per token), context strategy, tool design, guardrails, agent framework, prompt versioning. Owns the agent's behaviour; `forjate:data-store` owns where its memory lives. |
| Compliance & data governance | `forjate:compliance` | Data residency, legal retention, DPIA, OSS licences of chosen components, model-provider terms, evidence for audits. Separate from security on purpose: in regulated organisations a different reviewer signs it. |

Plus three cross-cutting pieces:

| Piece | Role |
|-------|------|
| `forjate:coordinator` (user-invocable `/usecase`) | Intake interview → brief → orchestrates planner + experts → assembles overlay → hands over for review. |
| `forjate:stage-planner` | Turns the brief into a `stage-plan.yaml`: scope, exit criteria and component tier for Crawl, Walk, Run. |
| `forjate:kustomize` (shared skill) | The only thing that knows *how* to write Forjate overlays: component lookup in `wiki/`, patch conventions, secrets `.env.example`, overlay tiers, `usecase.yaml` contract. Every expert loads it when it has to emit YAML. |
| `forjate:app-scaffold` (builder, not expert) | Generates the agent workload from the records: service skeleton (worker / API), Dockerfile, tool definitions, tests, `sync-app-image.yml` hook. Without it the builder ships infrastructure with no workload and Crawl never runs. |
| `forjate:context-pack` (shared skill + resolver script) | The single interface through which every skill receives external guidelines: corporate policies, tool-development standards, user rules. See §2.6. |

Roles deliberately **not** added: FinOps (absorbed by `forjate:business` + `forjate:devops`), SRE/observability (inside `forjate:devops` until Run), change management and adoption (inside `forjate:ux` + `forjate:business`). The approver / product owner is a human and is modelled as a manual gate, never as an agent.

All documents and artifacts are written in **English by default**; the coordinator asks the output language once during intake and records it in `brief.yaml` (`spec.language`). Every skill reads that field.

---

## 2. Design decisions (made now, revisited in Phase 5)

### 2.1 Packaging: one Claude Code plugin

The whole team ships as a single plugin named `forjate`, living in this repo under `plugins/forjate/` and listed in a marketplace file at the repo root so tenants (im-u, globant, any remote tenant) install it with `/plugin install forjate` and pin it like they pin the factory. Skills are named by role and surface as `forjate:<role>` (`forjate:coordinator`, `forjate:security`, ...), which gives namespacing without an invented prefix and keeps the names aligned with `forjate-wiki` and the future `forjate-catalog` MCP server. The plugin also carries the subagents, the resolver scripts, and the MCP server definition (Phase 5), so one version number covers the complete team.

```
plugins/forjate/
├── .claude-plugin/plugin.json   # name, version, description
├── skills/<role>/SKILL.md       # 13 skills, references/ and scripts/ per skill
├── agents/<role>.md             # one subagent per expert, loads its skill
├── scripts/builder/             # packs.py, validate.py, schemas/
└── .mcp.json                    # forjate-catalog server (Phase 5)
```

### 2.2 Skills vs subagents

| Unit | Implemented as | Why |
|------|----------------|-----|
| Expert knowledge (what to choose, why, references) | **Skill** (`plugins/forjate/skills/<area>/SKILL.md` + `references/` + `scripts/`) | Progressive disclosure: metadata always loaded, body on trigger, references on demand. Reusable from any runtime (Claude Code, Agent SDK, Cowork). Testable with the skill-creator eval loop. |
| Expert execution in isolation | **Subagent** (`plugins/forjate/agents/<area>.md`) that loads its skill | Keeps the coordinator's context clean; each expert runs with a fresh context, a restricted tool set, and returns only the decision record. |
| Coordinator | **User-invocable skill** that uses the `Agent` tool | The user talks to one thing. Forking/spawning is a runtime concern, not knowledge. |

Rule of thumb: **knowledge in skills, isolation in agents, contracts on disk.**

### 2.3 Inter-agent communication: files first, MCP second, A2A only if needed

- **Phase 1–4: file-based contracts.** Agents communicate through schema-validated YAML under `usecases/<name>/.builder/`. This is auditable, diffable, CI-validatable and runtime-agnostic. It is also exactly how `usecase.yaml` already works.
- **Phase 5: MCP server `forjate-catalog`.** Wrap what every expert needs to query: the wiki index, component capability matrix, `qmd` search, `kustomize build` dry-run. One server, read-mostly tools. This removes the duplicated "grep the catalog" logic from every skill and makes the experts usable from Claude.ai / Agent SDK too.
- **A2A: deferred.** It only pays off when experts run in different runtimes or organizations. Decide at the Phase 5 checkpoint with evidence, not up front.

### 2.4 Stage model

| Stage | Forjate tier | Scope | Defaults the experts lean on |
|-------|--------------|-------|------------------------------|
| **Crawl** (PoC) | Lab | Prove the automation works on real-shaped data, single user | `quickstart`-style, k3d via `ephemeral.sh`, Ollama or external LLM, Postgres, MinIO, no auth, placeholder secrets |
| **Walk** (pilot / MVP) | MVP | Real users, internal, single cluster | `bare-metal-starter` shape: ArgoCD, Sealed Secrets, GoTrue + oauth2-proxy, Prometheus + Grafana, PSA `baseline`, NetworkPolicies |
| **Run** (production) | Production | SLAs, audits, multi-tenant | External Secrets / Vault, Velero, PSA `restricted`, OTel pipeline, DB operators, `multi-tenant-pattern`, Cosign |

Every expert must answer **per stage**, not once. The stage planner fixes which stages are in scope for this use case (a one-off internal script may stop at Walk).

### 2.5 Structured artifacts (the review surface)

```
k8s/overlays/usecases/<name>/
├── .builder/
│   ├── brief.yaml              # intake: problem, actors, data, constraints, success metric
│   ├── stage-plan.yaml         # per stage: goal, exit criteria, in/out of scope
│   ├── decisions/
│   │   ├── architecture.yaml
│   │   ├── data-store.yaml
│   │   ├── data-pipeline.yaml
│   │   ├── security.yaml
│   │   ├── ux.yaml
│   │   ├── quality.yaml
│   │   └── devops.yaml
│   └── gates.yaml              # consolidated gate checklist Crawl→Walk→Run
├── usecase.yaml                # existing contract (seed/run/verify, outputs)
├── kustomization.yaml          # Crawl stage by default
├── stages/walk/ · stages/run/  # overlays-on-the-overlay, added when the stage is unlocked
├── namespaces/ · secrets/ · patches/ · configs/
└── README.md
```

Decision record schema (one per area, all share it):

```yaml
apiVersion: forjate.io/v0
kind: Decision
metadata: { area: data-store, usecase: <name>, author: forjate:data-store, version: 1 }
spec:
  stages:
    crawl:
      choice: [apps/databases/postgres, apps/minio/single-server]
      rationale: "..."
      alternatives: [{ component: apps/databases/lancedb, rejected_because: "..." }]
      risks: [{ id: R1, text: "...", mitigation: "..." }]
      gate_to_next: ["retention policy defined", "backup tested once"]
      constrained_by: ["pack:acme-platform#DATA-03"]   # which pack rule forced or shaped the choice
    walk: { ... }
    run:  { ... }
  open_questions: ["..."]      # things only the user can answer
  references: ["wiki/components/databases-postgres.md", "docs/storage-strategy.md"]
```

Schemas live in `scripts/builder/schemas/` and are validated in CI like `usecase.schema.json` is today.

### 2.6 Context packs — one interface for external guidelines

A **context pack** is a versioned bundle of guidelines that overrides the factory defaults: inherited corporate decisions, tool-development standards, security baselines, naming rules, or a single user's preferences. Packs are the mechanism by which "what the catalog recommends" becomes "what this organisation allows".

Design goals: same shape for every skill, machine-checkable where possible, prose where not, and traceable (every decision cites the rule that shaped it).

```
context-packs/<name>/
├── pack.yaml                 # manifest (below)
├── constraints.yaml          # structured, machine-checkable rules
└── guidelines/               # prose, loaded on demand by the skills it applies to
    ├── tool-development.md
    ├── security-baseline.md
    └── naming.md
```

```yaml
# pack.yaml
apiVersion: forjate.io/v0
kind: ContextPack
metadata:
  name: acme-platform
  version: 1.2.0
  scope: org            # org | team | usecase | user
  precedence: 20        # higher wins on conflict; factory defaults are 0
spec:
  applies_to: ["*"]     # or a list of skills: [security, ai-engineering]
  language: en
  sources:
    - id: DATA-03
      kind: constraint              # constraint | guideline | reference
      path: constraints.yaml#/rules/DATA-03
      enforce: must                 # must | should | may
      applies_to: [data-store, compliance]
    - id: TOOLS
      kind: guideline
      path: guidelines/tool-development.md
      enforce: should
      applies_to: [ai-engineering, app-scaffold]
```

```yaml
# constraints.yaml — the vocabulary is fixed so validate.py can check decisions against it
rules:
  DATA-03:  { type: deny_components,    value: [apps/databases/mongodb], reason: "no MongoDB licence in prod" }
  SEC-01:   { type: min_psa_level,       value: restricted, stages: [walk, run] }
  SEC-02:   { type: secrets_mechanism,   value: external-secrets, stages: [run] }
  AI-01:    { type: model_allowlist,     value: ["claude-*", "ollama/*"] }
  AI-02:    { type: data_egress,         value: none, data_classes: [pii, financial] }
  RES-01:   { type: data_residency,      value: eu }
  NAM-01:   { type: naming_pattern,      target: namespace, value: "^acme-[a-z0-9-]+$" }
```

**Layering and precedence.** Factory defaults (0) < org pack < team pack < use-case pack < user pack < explicit user instruction in the session. On conflict the highest precedence wins; a `must` from a lower layer that is overridden by a higher layer is logged as a warning in `gates.yaml` so the override is visible to reviewers. Packs can be local directories or remote git references pinned to a ref, exactly like components (`ssh://git@github.com/acme/platform-packs.git//security?ref=v1.2.0`), so corporate packs stay in private repos.

**Activation.** The coordinator records the active packs in `.builder/packs.yaml` (asked during intake, or auto-detected from `context-packs/` in the repo and from `~/.forjate/packs/` for user packs). `scripts/builder/packs.py resolve --for security` merges every active pack, filters by `applies_to`, applies precedence, and prints a compact `packs.resolved.yaml` for that skill only. Subagents never load whole packs; they get the resolved subset in their prompt.

**The same interface in every skill.** Each `SKILL.md` carries an identical "Context packs" section (templated from `skills/context-pack/references/section.md`): run the resolver for yourself, treat `must` as a hard constraint, treat `should` as the default unless you explain in `rationale` why not, cite rule ids in `constrained_by`, and raise an `open_question` instead of silently dropping a rule you cannot satisfy. `validate.py` then checks mechanically that no decision violates a `must` of a structured type, and that every cited rule id exists.

Packs are also how **tool-development guidelines** reach `forjate:ai-engineering` and `forjate:app-scaffold`, so a corporate "tools must be idempotent, typed, and logged through X" standard shapes the generated code without editing any skill.

---

## 3. Testing strategy (applies to every agent)

Mechanism, end to end: `evals.md`.

Three levels, all automated, all runnable locally and in CI.

| Level | What | Tooling | Gate |
|-------|------|---------|------|
| **L1 — skill evals** | 3–5 realistic prompts per skill, run with-skill vs without-skill, graded by assertions | skill-creator: `evals/evals.json`, `generate_review.py`, `aggregate_benchmark` | pass-rate with-skill > baseline; no assertion regresses between iterations |
| **L2 — contract tests** | Every artifact an agent emits validates against its schema and references only components that exist in `wiki/index.md` | `scripts/builder/validate.py` (PyYAML + jsonschema) in `.github/workflows/validate-usecases.yml` | 100 % schema-valid, 0 dangling component refs |
| **L3 — end-to-end** | Coordinator run on a golden use case produces an overlay that `kustomize build`s, passes `kubeconform`, and `ephemeral.sh up` returns 0 | existing CI + k3d job | verify Job exit 0 |
| **L4 — trigger evals** (Phase 5) | 20 should/should-not-trigger queries per skill | skill-creator `run_loop.py` | ≥ 90 % trigger accuracy on held-out set |

Lessons from Phase 0 and 1, binding for every later eval:

- **The baseline must be a real control.** The plugin lives in this repo, so a baseline worktree carries the skills on disk; `run.sh` strips `plugins/forjate/skills`, `agents` and `docs/use-case-builder` for the without-plugin configuration. Before that fix both configurations scored the same for the wrong reason.
- **Form assertions stop discriminating fast.** With the schema path in the prompt, a frontier model produces a valid artifact with or without the skill. Each eval needs at least two assertions on *judgement* (a pack rule cited, an `OPEN:` question raised, a stage skipped with a reason, a gate expressed as `ci`/`metric` rather than `manual`) next to the form checks, or the pass rate says nothing.
- **Run evals on Opus, record the model.** `run.sh` defaults to `--model opus` and the benchmark lists the models used; a session-limit hit is recorded as `is_error` and re-run, never counted as a failure.
- **Quality metrics travel with the benchmark.** Gate counts by check type, pack references and `OPEN:` lines are computed per run; they are where the skill's value showed when pass rates tied.
- **Assert consistency, not a fixed shape.** "Temporal at Walk" failed a record that chose a Postgres outbox at 200 messages/day with a sound argument; "a webhook implies an external surface" is what the eval was really after. When a with-skill run fails, read the record before touching the skill: half the time the assertion is the thing that is wrong.
- **Hung runs need a wall-clock deadline.** A `sleep`-based watchdog does not fire while a laptop is suspended; `run.sh` polls the clock every 15 s and kills on the deadline. Keep the machine awake (`caffeinate -i -s`) for the length of a batch.

Assertion style for L1: objective and named, e.g. `recommends-postgres-for-crawl-state`, `declares-retention-per-stage`, `no-component-outside-catalog`, `gate-to-walk-has-backup-check`, `answers-in-schema`. Every expert additionally gets one **pack eval**: the same golden prompt with a pack that forbids its default choice, asserting `respects-pack-must`, `cites-pack-rule`, `raises-open-question-on-unsatisfiable-rule`. Subjective quality (tone, clarity) is reviewed by the human in the eval viewer, never forced into assertions.

### Golden use cases (fixtures for L2/L3, reused across phases)

| Id | Use case | Why it is a good fixture |
|----|----------|--------------------------|
| G1 | **Invoice intake**: PDFs land in a mailbox/folder, extract fields, validate against ERP, push to accounting API | Exercises pipeline (Docling), long-term memory (Postgres), integration (external API), regulated-ish data (PII), human review UX |
| G2 | **Support copilot on Telegram** with escalation to a durable workflow | Exercises chat UX, short-term memory (Redis/Mongo), Temporal, LiteLLM, auth to the Temporal UI |
| G3 | **DB migration A→B** (already exists in `usecases/`) | Regression anchor; proves the builder can reproduce an existing contract |

---

## 4. Phases

Each phase ends with a demo on the golden use cases and a checkpoint commit tagged `builder-p<N>`.

### Phase 0 — Foundations (≈ 1 week)

Goal: contracts, catalog and harness exist before any expert is written.

1. **Plugin skeleton**: `plugins/forjate/` with manifest, empty `skills/` and `agents/`, marketplace entry at repo root, and `docs/use-case-builder/`. Verify `/plugin install` from a clean checkout works before writing any skill.
2. **Schemas**: `brief.schema.json`, `stage-plan.schema.json`, `decision.schema.json`, `gates.schema.json`. Document them in `docs/use-case-builder/contracts.md`.
3. **Component capability matrix**: extend `scripts/wiki-compile.py` to emit `wiki/catalog.json` with, per component: category, stage fitness (`crawl|walk|run`), data class it may hold, PSA-restricted compatibility, secrets mechanism, maturity. Starts hand-curated in a sidecar `catalog-overrides.yaml`, merged at compile time. This is the single source every expert reads.
4. **Context-pack interface**: `pack.schema.json`, `constraints.schema.json` with the fixed rule vocabulary, `scripts/builder/packs.py` (resolve, lint, diff), `forjate:context-pack` shared skill with the templated SKILL.md section, and two fixture packs: `context-packs/examples/regulated-corp/` and `context-packs/examples/solo-dev/`.
5. **`forjate:kustomize` shared skill**: how to write an overlay that satisfies `docs/overlays/CONVENTION.md` tier Mínimo → Advanced, how to fill `usecase.yaml`, `.env.example` rules, patch patterns. References: CONVENTION.md, ephemeral README, 3 existing overlays.
6. **Eval harness**: `scripts/builder/evals/` with a thin wrapper around skill-creator's runner so `make builder-evals SKILL=data-store` works. Golden use-case fixtures G1–G3 as `brief.yaml` files.
7. **CI**: `validate-usecases.yml` also validates `.builder/**` artifacts and `context-packs/**`.

Tests: L2 on fixtures; `forjate:kustomize` L1 with 3 prompts ("add Redis to this overlay", "turn this component list into a Walk-stage kustomization", "write the usecase.yaml for G3").

Exit: schemas merged, `catalog.json` generated and linted, `packs.py resolve` round-trips both fixture packs, `forjate:kustomize` beats baseline on its evals.

### Phase 1 — Coordinator + Stage planner (≈ 1 week)

Goal: from a one-paragraph problem to `brief.yaml` + `stage-plan.yaml`, with no experts yet.

1. **`forjate:stage-planner`** skill + agent. Input: brief. Output: stage plan with exit criteria that are *observable* (a verify Job can check them). References: `lab-to-production.md`, CONVENTION tiers.
2. **`forjate:coordinator`** skill (`/usecase <problem>`): intake interview (max 6 questions, uses `AskUserQuestion`; always asks output language and active context packs), writes brief and `.builder/packs.yaml`, spawns planner, presents plan for approval, then stops. Expert fan-out is stubbed with a "not yet available" record so the pipeline shape is complete from day one.
3. **Session resume**: coordinator detects an existing `.builder/` and resumes from the last valid artifact instead of re-interviewing.

Tests:
- Planner L1: G1/G2/G3 prompts. Assertions: `three-stages-or-explicit-skip`, `exit-criteria-are-observable`, `crawl-uses-ephemeral-runner`, `run-stage-mentions-psa-restricted-when-regulated`.
- Coordinator L1: "automate invoice intake" cold start; "resume G2"; a vague prompt that should trigger clarifying questions. Assertions: `asks-at-most-6-questions`, `brief-validates`, `does-not-invent-components`.
- L2 on all emitted artifacts.

Exit: a user can run `/forjate:coordinator` and get a reviewed brief + stage plan committed under `.builder/`.

**Done 2026-10-02 (tag `builder-p1`).** Opus, baseline with the plugin stripped from the worktree; tables in `benchmarks/`. Planner: with skill 100 % on 3 evals, baseline 97 % (lists non-expert roles, skips `business`); the skill cites pack rules 3× more on the regulated case and raises `OPEN:` questions the baseline never does. Coordinator: with skill 100 % on 3 evals, baseline 42 % (no derived name, fabricated expert records, no assumptions recorded) at 2–8× the cost. With the plugin the coordinator delegates to `forjate:stage-planner` (confirmed in `subagent_stats`) and writes the report in the brief's language.

### Phase 2 — Core experts: business, architecture, AI engineering, data store, data pipeline (≈ 2.5 weeks)

Goal: the experts whose decisions constrain everything else. `forjate:business` runs **first** (its KPI and cost envelope bound every other record); the other four run in parallel after it.

0. **`forjate:business`**: value hypothesis, success KPI per stage, actors and systems of record, as-is process with exceptions and SLAs, cost per stage from `lab-to-production.md`, go/no-go recommendation. Output feeds `brief.yaml` (enriched) and `gates.yaml` (business gates).

1. **`forjate:architecture`**: topology patterns (request/response agent, chat + Temporal, event-driven CDC, batch), integration catalog (webhook, REST, broker, CDC), apification guidance (when the use case must expose an API, auth in front of it). References: `agentic-simple-workflow`, `agentic-orchestration`, `cdc-event-sourcing`, `service-integration.md`.
2. **`forjate:data-store`**: memory taxonomy (session, working, episodic, semantic, artifacts) → component mapping (Redis, Postgres, Mongo, LanceDB/Milvus, MinIO), retention, backup per stage. References: `storage-strategy.md`, wiki pages of each DB.
3. **`forjate:data-pipeline`**: ingestion patterns, Docling for documents, Debezium bundles for CDC, NATS/RabbitMQ selection, seed-Job design for the ephemeral env, idempotency.
3b. **`forjate:ai-engineering`**: model selection matrix (Ollama/vLLM local vs API via LiteLLM), context and memory strategy (hands storage choice to `forjate:data-store`), tool design rules, guardrails, prompt/version management, cost per 1k requests per stage. Consumes tool-development guidelines from packs.
4. Coordinator wires the four in **parallel** (single Agent fan-out), then runs a **consistency pass**: a lightweight check that the three records reference compatible components (e.g. pipeline says NATS, architecture says RabbitMQ → open question raised, not silently resolved).

Tests:
- Each expert L1 with G1–G3 (+1 adversarial prompt per expert: e.g. "store chat history in MinIO" should be pushed back with rationale). Assertions per area, e.g. data-store: `separates-short-and-long-term`, `retention-per-stage`, `vector-store-only-if-semantic-memory-needed`.
- L2 + new **cross-record consistency check** in `validate.py`.
- L3 smoke: coordinator on G3 regenerates a `usecase.yaml` equivalent to the committed one (diff ignoring ordering).

Exit: G1 and G2 have five validated decision records and a Crawl `kustomization.yaml` that builds.

**Done 2026-10-03 (tag `builder-p2`).** Five expert skills, agents and eval suites; cross-record consistency as check 6 of `validate.py` (18 tests); coordinator fan-out in two waves with the consistency pass; `experts.md`. Evals on Opus, baseline with the plugin stripped, 5 evals per expert (3 golden briefs, 1 adversarial, 1 pack), tables in `benchmarks/`:

| Expert | with skill | baseline | What the baseline misses |
|--------|-----------|----------|--------------------------|
| business | 100 % | 73 % | as-is exceptions, go/no-go per stage, numbers derived from the brief's volume, baseline kept under pressure |
| architecture | 100 % | 80 % | integrations named with a pattern, workloads for the scaffolder, closed Crawl surface, durability at Run instead of a cron monolith |
| ai-engineering | 100 % | 83 % | structured output, untrusted inputs, gated write tools, memory requested by kind, cost per 1k, eval strategy |
| data-store | 100 % | 79 % | one store per memory kind and stage, short vs long term separated, backup ladder, systems of record |
| data-pipeline | 100 % (97 % before the CDC fix) | 68 % | batch Crawl with a seeded verify, live pattern at Walk, source-derived idempotency key, seed that represents the exceptions |

Quality metrics (open questions caused by a rule, pack refs, automated gates) favour the skill on every pack eval even where pass rates tie. Three evals tie at 100 % in both configurations (`pack-api-only`, `pack-no-docling`, `pack-no-temporal`): a frontier model honours a pack it is pointed at; the value of the skill there is in the record's shape, not the verdict, and those evals need harder assertions in Phase 5. The one with-skill miss (`data-pipeline` adversarial: CDC accepted at Walk "on the requester's instruction") was fixed in the skill's CDC rule and re-run as iteration 2. The Crawl `kustomization.yaml` for G1/G2 is Phase 4 (assembly); the five records of each were validated together with zero cross-record conflicts.

Lessons added to §3: assertions must check consistency between fields (webhook ⇒ external surface) rather than one fixed shape, or they punish a record that reasons better than the eval author; a `claude -p` that hangs while the laptop sleeps is only caught by a wall-clock deadline (`run.sh` polls instead of sleeping; keep the machine awake with `caffeinate` for a batch).

### Phase 3 — Governance experts: security, compliance, quality, devops (≈ 2.5 weeks)

Goal: the experts that turn "it works" into "it can ship".

1. **`forjate:security`**: data classification questionnaire (PII / financial / health / none), secrets mechanism ladder (secretGenerator → Sealed Secrets → External Secrets / Vault) mapped to the four mechanisms in `wiki/concepts/secret-strategy.md`, auth surface (GoTrue + oauth2-proxy), NetworkPolicy default-deny, PSA level per stage, audit trail (CDC as evidence), LLM-specific threats (prompt injection, data exfiltration via tools, model egress). Written so a corporate security reviewer can read the record as-is.
1b. **`forjate:compliance`**: data residency and transfer, legal retention vs the retention `forjate:data-store` chose, DPIA checklist, OSS licence scan of chosen components (from `catalog.json`), model-provider terms, evidence bundle for auditors. Pushes back on `forjate:ai-engineering` when a model provider violates a residency or egress rule.
2. **`forjate:quality`**: gate design (what must be true to unlock Walk and Run), verify-Job design, test pyramid for the agent code, LLM eval strategy (golden sets, judge rubrics, regression on prompts), observability as a quality signal. Owns `gates.yaml` consolidation.
3. **`forjate:devops`**: environment ladder (ephemeral k3d → shared cluster → prod), GitOps with ArgoCD, image build + `sync-app-image.yml`, Sealed Secrets rotation, Prometheus/Grafana baseline, rollback runbook, cost note per stage.
4. **Gates become executable**: `gates.yaml` entries that map to a verify Job or CI check get a `check:` field; the coordinator reports which gates are automated vs manual.

Tests:
- L1 per expert, including regulated variants of G1 ("invoices contain bank account numbers, we are under PCI-like audit"). Assertions e.g. security: `psa-restricted-at-run`, `no-plaintext-secrets-in-run`, `names-data-class`, `prompt-injection-mitigation-present`; quality: `every-gate-is-observable`, `verify-job-defined`; devops: `argocd-at-walk-or-later`, `rollback-steps-present`.
- L2 + gate schema.
- L3: G1 Crawl overlay passes `ephemeral.sh up` with the verify Job the quality expert designed.

Exit: all ten records exist for G1/G2; `gates.yaml` consolidated; security record reviewed by a human once and feedback folded back.

**Done 2026-10-03 (tag `builder-p3`).** Four governance skills, agents and eval suites; the 15 lessons of `tenant-patterns.md` folded in as rules with their evidence (security 9, 10, 13, 15; devops 11, 12, 14; kustomize 1 to 6 and the default-deny NetworkPolicy; data-store 7, 8). `validate.py` check 6 now maps `secrets_mechanism` onto the secrets components, treats `network_policy`, `backup` and `auth_in_front` as shared settings and flags one gate id claimed with two texts; check 7 warns when `gates.yaml` lacks a record's gate (32 tests). Gates are executable: `forjate:quality` has a `consolidate` mode that writes `gates.yaml` with a `check` on every gate (`verify-job`, `ci`, `metric` with the ref conventions in its reference, `manual` naming the signer) and the pack overrides; the coordinator runs the nine experts in wave 2, the consistency pass, then quality in wave 3, and the report counts automated versus manual gates per transition. Evals on Opus, baseline with the plugin stripped, 5 evals per expert (3 golden briefs with the core experts' records as fixtures, 1 adversarial, 1 pack layered over `regulated-corp`), tables in `benchmarks/`:

| Expert | with skill | baseline | What the baseline misses |
|--------|-----------|----------|--------------------------|
| security | 100 % | 75 % | secrets ladder per stage, default-deny from Walk, injection via PDFs as a threat, the write-tool gate, tag deploys; it accepts an API key in a configMap literal when asked |
| compliance | 100 % | 73 % | DPIA, licence inventory with MinIO as AGPL, DPA with the provider, legal basis, subject rights, a human signer |
| quality | 100 % | 71 % | idempotency and the exception path in the verify Job, the KPI line, rules judge with an injection suite, regression on prompt change, justified manual gates; it makes every gate manual when asked |
| devops | 100 % | 72 % | Crawl as the ephemeral runner only, tag revision and pinned refs, distinct Walk environment, `yq` write-back, scripted rotation, rehearsal flags; it installs ArgoCD at Crawl and tracks `develop` when asked |

Two with-skill misses were the evals' fault and were fixed in the assertions, not the skills: security left `data_egress: none` and raised a stage-blocking question where the AI-engineering fixture said `anonymized` (the assertion demanded silent agreement); compliance set `transfer_mechanism: unknown` at Walk because IMAP and Odoo are hops whose hosting region nobody stated, and raised it (the assertion demanded `none`). One with-skill miss was a fixture bug: pack evals copied records citing `regulated-corp` without activating it; the fixture packs are now team packs (precedence 30) layered over `regulated-corp`, which also exercises the resolver's override path. `pack-audit-graded` ties at 100 %, like the phase 2 pack ties: a frontier model honours a pack it is pointed at. Not done in this phase: the L3 run of the G1 Crawl overlay with the verify Job (needs the assembly step, phase 4) and the human review of a security record (the reviewer is Sebas; the records under `evals-workspace/security/iteration-1/*/with_skill/` are the candidates).

Lessons added to §3: an expert that raises a question instead of mirroring another record is doing its job, so cross-record assertions must accept "agrees or asks"; `usecase_valid` passes on warnings and therefore does not discriminate a single-expert run, so every eval needs judgement assertions beside it; fixture records that cite a pack bind every eval that copies them to activating that pack.

### Phase 4 — UX expert + full assembly (≈ 1.5 weeks)

Goal: the coordinator produces a complete, deployable Crawl overlay and a Walk/Run upgrade path end-to-end.

1. **`forjate:ux`**: surface selection per stage (CLI/notebook for Crawl, Open WebUI or Telegram for Walk, custom web/API for Run), human-in-the-loop checkpoints, feedback capture (Formbricks is in the catalog), latency/streaming expectations, failure UX.
1b. **`forjate:app-scaffold`**: from the records, generate the workload: service skeleton (FastAPI agent, Temporal worker, or batch Job as `forjate:architecture` decided), tool stubs typed per `forjate:ai-engineering`, Dockerfile, unit tests, and the image reference the overlay patches. Pack guidelines on tool development apply here verbatim.
2. **Assembly step** in the coordinator: merges records → calls `forjate:kustomize` to write `kustomization.yaml`, `namespaces/`, `patches/`, `secrets/*.env.example`, `usecase.yaml`, `stages/walk/`, `stages/run/`, README with the decision summary.
2b. **Tenant target** (added after the im-u survey, `tenant-patterns.md`): `--target tenant <repo>` emits the tenant-root shape with SSH refs pinned to one tag, `$patch: delete` for placeholder Secrets, ArgoCD Application and repo-server SSH wiring at Walk, `images:` as the write-back surface. Without it the builder's output cannot be consumed by the two real tenants.
2c. **Plaintext-credential scan** as a `ci` gate: `scripts/builder/secret-scan.py`, wired into `validate-kustomize.yml`.
3. **Review mode**: `/usecase review <name>` prints a human-readable report (per-area decisions, open questions, gates, cost per stage) — the artifact a stakeholder reads before approving a stage. Inside a tenant repo it also lists drift between the tenant's `CLAUDE.md` and its tree.
4. **Docs**: `docs/use-case-builder/` (overview, contracts, how to add an expert), entry in `docs/learning-path.md`.

Tests:
- `forjate:ux` L1 (G1–G3 + "no UI needed, it is a nightly batch" negative case).
- `forjate:app-scaffold` L1: generated service builds, its tests pass, tool signatures match the AI-engineering record.
- L3 full: coordinator from cold on G1 and G2 → `kustomize build` + `kubeconform` + `ephemeral.sh up` green in CI (k3d job, nightly, not per-PR).
- Walk stage: `kustomize build stages/walk` green, and the tenant-target output builds against the factory at the pinned tag; a manual deploy on the homelab cluster once, documented.

Exit: a new user can go from problem statement to a running Crawl environment in one session, and read a report that explains every choice.

### Phase 5 — Hardening and protocol decision (≈ 2 weeks)

0. **De-bias the skills: roles and properties, not component names.** Review on 2026-10-07 counted component names against role or catalog references per skill: data-store 90/4, devops 74/1, architecture 71/2, compliance 55/4, data-pipeline 55/2, security 48/1, ai-engineering 41/1. The skills were written against today's catalog; as it grows, a ladder that says "Walk → `apps/sealed-secrets`" or an assertion named `recommends-postgres-for-crawl-state` keeps a better component from ever being chosen. The fix moves the role→component mapping to the one place that already owns it, the catalog:
   - Skills ask by **role and property** (`session-memory`, `secrets.mechanism >= sealed`, `local-model`, `durable-workflows`) and resolve the component from `wiki/catalog.json` at run time; with several candidates they apply the selection criteria (stage fitness, licence, maturity, GPU, HA, data class) and record the alternatives, which they already do well.
   - `catalog-overrides.yaml` gains the properties the skills hard-code today: `secrets.mechanism`, `gpu_required`, `ha` (single | replicated | operator), `psa_restricted`, `data_classes`. `validate.py` ranks mechanisms through the catalog instead of a table in the code.
   - Concrete examples stay, as a generated `references/catalog-snapshot.md` per skill ("today the catalog resolves `session-memory` to Redis"), compiled by `wiki-compile.py` and labelled as a snapshot, never as a rule. Prose keeps naming a component only where the catalog has a single option for the role.
   - Evals assert roles, not names: new assertion type `choice_has_role`; names remain only for single-option roles. Re-run every suite after the rewrite.
   - `scripts/builder/skill-lint.py` in CI flags component names in `SKILL.md` and references outside snapshot files.
   Rules of judgement that use a component as an illustration ("session memory is a TTL key-value problem") are not the target; stage→component tables and assertions are.
0b. **PSA level at Walk on shared clusters.** Human review of the phase 3 security record (2026-10-07): Walk could enforce `restricted`, but shared infrastructure (operators, storage, inference) needs exceptions and the rule for them is not settled. Today the skill enforces `baseline` at Walk with `restricted` as warn/audit, a pack raises it, and shared components are exceptions in their own namespaces. Decide the rule with one real cluster (im-u) and fold it into the security skill and `stage-defaults.md`. Same review: the egress allow-list was cut to external hostnames at Walk, with the per-workload matrix as a Run recommendation; Crawl without NetworkPolicy confirmed.
1. **Description optimization** for all thirteen skills with the trigger-eval loop (L4). Experts should not fire on general k8s questions; the coordinator should fire on "automate", "use case", "PoC", "I want an agent that…".
2. **`forjate-catalog` MCP server** (`mcp-builder` skill): tools `search_catalog`, `get_component`, `list_overlays`, `validate_decision`, `kustomize_dry_run`. Replace file-grepping in the skills with MCP calls; keep the file fallback.
3. **Protocol checkpoint**: measure whether any expert needs to run outside Claude Code (Agent SDK service, Cowork). If yes, write an ADR on A2A vs MCP-tools for that boundary. If no, record "not needed yet" and move on.
4. **Memory across runs**: the coordinator appends outcome notes (what shipped, what gate failed) to `.builder/log.md`, and `wiki-compile` indexes `.builder/` decisions so future runs can cite precedent ("G1 chose Docling for PDFs because…").
5. Release the plugin: bump `plugin.json` version, tag the factory `v1.x.0`, and install it in the im-u tenant as the first remote consumer.

Tests: L4 on every skill; MCP server contract tests; full L1–L3 re-run as regression.

---

## 5. Definition of done per agent (checklist)

An agent/skill is "done" for a phase only when all of these hold:

- [ ] `SKILL.md` < 500 lines, "pushy" description, references split by stage or domain under `references/`.
- [ ] Emits its artifact in schema and nothing else to the coordinator.
- [ ] Carries the templated "Context packs" section and passes its pack eval.
- [ ] `evals/evals.json` with ≥ 3 prompts incl. one adversarial, assertions named and objective.
- [ ] Beats the no-skill baseline on pass-rate in the last iteration; benchmark.md committed under `<skill>-workspace/` (git-ignored outputs, kept benchmark).
- [ ] L2 validation wired in CI.
- [ ] Documented in `docs/use-case-builder/experts.md` with: inputs, outputs, when it pushes back, what it will never decide alone.

---

## 6. Risks and how the plan absorbs them

| Risk | Mitigation |
|------|------------|
| Experts contradict each other | Consistency pass (Phase 2) + open questions surfaced to the user instead of silent resolution |
| Skills drift from the catalog | `catalog.json` is generated; `validate.py` fails on any component not in it; `wiki-lint` already flags stale pages |
| Over-engineering for Crawl | Stage planner is allowed to mark stages out of scope; experts must give a "boring default" first |
| Evals become theater | Baseline comparison is mandatory; assertions are reviewed by a human in the viewer each iteration |
| Context blow-up in the coordinator | Experts run as subagents returning only records; coordinator never reads expert transcripts |
| A2A/MCP decided too early | Deferred to Phase 5 with a measurable trigger |
| Packs silently override each other | Precedence is explicit, overrides of a `must` are logged in `gates.yaml`, decisions cite rule ids |
| Thirteen agents is a lot of context and latency | Experts are subagents returning records only; business runs first, the rest fan out in parallel; stage planner can mark experts out of scope for small use cases |

---

## 7. Timeline

| Phase | Weeks | Milestone tag |
|-------|-------|---------------|
| 0 Foundations | 1 | `builder-p0` |
| 1 Coordinator + planner | 1 | `builder-p1` |
| 2 Core experts | 2.5 | `builder-p2` |
| 3 Governance experts | 2.5 (done in 1 day) | `builder-p3` |
| 4 UX + assembly | 1.5 | `builder-p4` |
| 5 Hardening + protocol | 2 | `builder-p5` / `v1.x.0` |

Total ≈ 10.5 weeks of focused work; phases 2 and 3 parallelize across people if available.

# Use-Case Builder — execution plan

> An agentic team that takes a one-paragraph business problem and turns it into a Forjate overlay, staged Crawl → Walk → Run, with structured, reviewable artifacts at every step.

Status: **Phase 4 done (tag `builder-p4`, 2026-10-11); phase 5 planned as issues labelled `builder-p5` (2026-10-29)** · Owner: Sebas · Created: 2026-10-02

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
- **The answer must not be on disk.** The golden use cases are committed with their records, apps and overlays; a worktree created from `HEAD` carries them, and both configurations scored on what they found. `run.sh` strips them from every worktree and a skill lists in `evals/<skill>/worktree-keep` what it needs as input. Likewise the quality metrics skip records byte-identical to a fixture.
- **Builders need a bigger turn budget and a longer clock.** A scaffold or an assembly writes dozens of files: 40 turns end in `error_max_turns`, 1800 s cut a 120-turn run. `--max-turns 150 --timeout 5400` for the builders, and the runner's kill path must not abort the batch.
- **A grep that matches the sentence saying the opposite.** "no [token] checkpoint", a comment explaining why no `docker build` step exists, a lowercase header constant: four with-skill misses in phase 4 were assertions reading the text of a correct record. Match the flag at the end of the line, ignore comments, grep case-insensitively, accept a helper call where a literal line was expected.
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
1c. **Gates runner** (decided 2026-10-09). `scripts/gates/gates.py run <usecase> --transition crawl->walk` reads `gates.yaml` and runs every `ci` gate as `scripts/gates/checks/<ref>.sh` (exit code per gate, table pass/fail/manual/skipped, exit 1 on a failed `ci`); `verify-job` runs `ephemeral.sh validate` when a cluster exists, else `skipped`; `metric` reads `kpi_metric_source`, else `pending`; `manual` prints gate, signer and ref, never blocks. The check directory is the enum: `validate.py` fails a `ci` gate whose ref has no script. First checks: `netpol-check`, `psa-check`, `secret-scan`, `env-example-check`, `ref-pinning-check`, `stage-overlay-builds`, `argocd-revision-check`. Reusable workflow `.github/workflows/gates.yml` (`workflow_call`, inputs `usecase`, `transition`) so tenants call it by tag. Operator rehearsals stay `manual`.
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

**Done 2026-10-11 (tag `builder-p4`).** The ux expert, the app-scaffold builder, the assembly step with the tenant target, the gates runner, the secret scan and the review-mode drift check. Both golden use cases are committed end to end under `k8s/overlays/usecases/{invoice-intake,support-copilot}/`: the ten records and `gates.yaml`, `app/` (the workload with typed tools, a deterministic model double for CI, seed and verify scripts, tests, Dockerfile, workflows on the shared templates `@v1`), `.builder/scaffold.yaml`, the Crawl root, `usecase.yaml` with `spec.build`, `stages/walk` and `stages/run`.

L3, run on the laptop's k3d: `ephemeral.sh up invoice-intake` builds the image, imports it, seeds 20 PDFs, runs the intake against Docling, Postgres, MinIO and the ERP stub and passes the 9 assertions of the quality record's verify Job (`KPI straight_through_rate=0.75`, `EVAL field_accuracy=1.0`); `support-copilot` passes its 12 (`KPI resolved_without_human_rate=0.6`). `gates.py run <name> --transition 'crawl->walk'` exits 0 on both against the live environment (invoice-intake 16 pass, 1 skipped, 4 manual; support-copilot 14 pass, 2 manual), with the measured metrics written to `.builder/metrics.yaml`. Every stage overlay builds and passes kubeconform (invoice-intake walk 267 resources, run 328; support-copilot walk 224). The tenant target of invoice-intake builds against the factory at `v1.1.0` (262 resources, kubeconform clean, every ref pinned). `tenant-drift.py` on the real im-u tenant lists the documented `gitops/` tree that does not exist, one dead namespace directory and seven branch refs.

Evals on Opus, baseline with the plugin stripped and the golden use cases removed from every worktree:

| Skill | with skill | baseline | What the baseline misses |
|-------|-----------|----------|--------------------------|
| ux | 100 % | 64 % | no surface at Crawl, the Telegram channel at Walk, deterministic handoffs instead of token approvals, feedback in the channel, numeric latency budgets, failure lines, the walkthrough or shadow period, the CSV named as the exception surface when the requester says "no UI" |
| app-scaffold | 99 % | 88 % | the shared CI templates (the baseline hand-rolls `docker/build-push-action` and a bare Trivy step when asked), the KPI line, the FastAPI surface; the one with-skill miss is a `pydantic-core` wheel that does not build on the grading host |
| kustomize (4 evals, incl. the assembly) | 100 % | 97 % | the baseline assembly ran out of turns at 151 (18 USD against 8, 1655 s against 935) and left no README and a registry path in `spec.build`; the three phase-0 evals tie at 100 % |
| coordinator (`review-tenant-drift` only) | 100 % | 100 % | a tie: a frontier model reading the fixture tree names the drift too; the skill is 43 % cheaper and 12 turns shorter; the assertions need tightening in phase 5 (L4) |

Three eval iterations were discarded, all for the harness and none for the skills: a 40-turn budget that ends a scaffold in `error_max_turns` (now `--max-turns 150` and `--timeout 5400` for the builders), the account's session limit, and the golden use cases committed with their records and apps while a batch ran, which put the answer on disk for both configurations (`run.sh` now strips them; `evals/<skill>/worktree-keep` preserves what a skill needs as input). Four with-skill misses were the assertions' fault and were fixed after reading the records: a grep that matched "no [token] checkpoint" as a token checkpoint, comments explaining why no `docker build` step is written, a lowercase header constant, a `kpi()` helper instead of a literal line.

Not done in this phase, carried to phase 5: the Walk scaffold (`review-api`, `intake-worker`, the escalation worker and the Telegram transport), so `stages/walk` serves the surface its Ingress already declares; the nightly L3 workflow run once in GitHub Actions; the coordinator's cold start run end to end with agents (the L3 of the coordinator; nightly, not per PR); Velero in the catalog. Found on the way: `quay.io/minio/minio:latest` no longer resolves, so `apps/minio/dev` pins the Bitnami legacy build; kustomize refuses `../..` from `stages/walk` as a cycle, so a stage overlay recomposes the root from its parts.

### Phase 5 — Hardening and protocol decision (≈ 2 weeks)

0. **De-bias the skills: roles and properties, not component names.** Review on 2026-10-07 counted component names against role or catalog references per skill: data-store 90/4, devops 74/1, architecture 71/2, compliance 55/4, data-pipeline 55/2, security 48/1, ai-engineering 41/1. The skills were written against today's catalog; as it grows, a ladder that says "Walk → `apps/sealed-secrets`" or an assertion named `recommends-postgres-for-crawl-state` keeps a better component from ever being chosen. The fix moves the role→component mapping to the one place that already owns it, the catalog:
   - Skills ask by **role and property** (`session-memory`, `secrets.mechanism >= sealed`, `local-model`, `durable-workflows`) and resolve the component from `wiki/catalog.json` at run time; with several candidates they apply the selection criteria (stage fitness, licence, maturity, GPU, HA, data class) and record the alternatives, which they already do well.
   - `catalog-overrides.yaml` gains the properties the skills hard-code today: `secrets.mechanism`, `gpu_required`, `ha` (single | replicated | operator), `psa_restricted`, `data_classes`. `validate.py` ranks mechanisms through the catalog instead of a table in the code.
   - Concrete examples stay, as a generated `references/catalog-snapshot.md` per skill ("today the catalog resolves `session-memory` to Redis"), compiled by `wiki-compile.py` and labelled as a snapshot, never as a rule. Prose keeps naming a component only where the catalog has a single option for the role.
   - Evals assert roles, not names: new assertion type `choice_has_role`; names remain only for single-option roles. Re-run every suite after the rewrite.
   - `scripts/builder/skill-lint.py` in CI flags component names in `SKILL.md` and references outside snapshot files.
   Rules of judgement that use a component as an illustration ("session memory is a TTL key-value problem") are not the target; stage→component tables and assertions are.
0b. **PSA level at Walk on shared clusters.** Human review of the phase 3 security record (2026-10-07): Walk could enforce `restricted`, but shared infrastructure (operators, storage, inference) needs exceptions. **Decided 2026-10-29**: `restricted` at Walk is too strict for now. Walk enforces `baseline` with `restricted` as warn and audit, Run enforces `restricted`, a pack can raise Walk, and shared components run in their own namespaces at their own level as recorded exceptions that never lower the use case's namespace. No real cluster is needed to decide it. **Done 2026-10-29 (#22)**: the mechanics are in the security reference, the record (`psa_exceptions`), the catalog, the validator and the kustomize assembly; see below. Same review: the egress allow-list was cut to external hostnames at Walk, with the per-workload matrix as a Run recommendation; Crawl without NetworkPolicy confirmed.
0c. **Fold the enterprise governance posture into the skills' judgement.** `context-packs/examples/enterprise-in-a-box` and `docs/agentic-reference-architecture.md` (2026-10-09) carry the posture as rules and prose; the brief now has `autonomy`, `risk_profile`, `isolation` and `constraints.open_standards_required`. While the skills are rewritten for 0, add the rules those documents imply: ai-engineering (execution bounds, intent validation, kill switch, semantic-memory strategy as compiled knowledge vs runtime retrieval vs API lookup); data-store (memory scopes); quality (audit artifacts per action as a gate, the seven evaluation dimensions); ux (review that validates, control levels by persona, disclosure); business (RACI, operating model, the three adoption frictions); devops (severities, shadow-agent structure); stage-planner (autonomy ceiling per stage, security in week one). Each as a rule with its reason, not a checklist; the pack stays the way an organisation turns the posture on.
1. **Description optimization** for all thirteen skills with the trigger-eval loop (L4). Experts should not fire on general k8s questions; the coordinator should fire on "automate", "use case", "PoC", "I want an agent that…".
2. **`forjate-catalog` MCP server** (`mcp-builder` skill): tools `search_catalog`, `get_component`, `list_overlays`, `validate_decision`, `kustomize_dry_run`. Replace file-grepping in the skills with MCP calls; keep the file fallback.
3. **Protocol checkpoint**: measure whether any expert needs to run outside Claude Code (Agent SDK service, Cowork). If yes, write an ADR on A2A vs MCP-tools for that boundary. If no, record "not needed yet" and move on.
4. **Memory across runs**: the coordinator appends outcome notes (what shipped, what gate failed) to `.builder/log.md`, and `wiki-compile` indexes `.builder/` decisions so future runs can cite precedent ("G1 chose Docling for PDFs because…").
5. Release the plugin: bump `plugin.json` version, tag the factory `v1.x.0`, and install it in one real tenant as the first remote consumer (globant/iac, the homelab or im-u, chosen at release time).

Tests: L4 on every skill; MCP server contract tests; full L1–L3 re-run as regression.

**Backlog (2026-10-29).** Phase 5 runs as GitHub issues labelled `builder-p5`, one PR each against `main`, each with its kick-off prompt, model and acceptance criteria; the shared rules and the model guidance are in `next-phase-prompt.md`. Items 0 and 0c are one task because they rewrite the same files. Item 2 starts with an ADR on what to reuse, which language and how to deploy; the server, if one is written, lives in its own AItizate repository and is deployed with forjate.

| Issue | Task | Blocked by | Model |
|-------|------|-----------|-------|
| #21 | L3 nightly run once in GitHub Actions, runtime recorded | — | Sonnet |
| #22 | PSA exceptions for shared components at Walk (0b) — **done 2026-10-29**, see below | — | Opus |
| #23 | Catalog capabilities and properties, `skill-lint`, `choice_has_capability` (0, infrastructure) — **done 2026-10-29**, see below | — | Fable 5.1 |
| #27 | Every skill rewritten to ask by role, governance posture folded in (0 + 0c) | #23, #22 | Fable 5.1 writes, Opus evals |
| #24 | Walk scaffold for invoice-intake | — | Opus |
| #25 | Walk scaffold for support-copilot | — | Opus |
| #28 | Coordinator cold start end to end (L3) | #27 | Opus |
| #6 | Velero in the catalog | — | Sonnet |
| #34 | Skill and checker to curate a component's capabilities and properties | #23 | Fable 5.1 (skill), Sonnet (checker) |
| #29 | Trigger evals and description optimisation (1) | #27 | Opus |
| #26 | ADR: catalog MCP server, reuse, language, A2A (2 and 3) | — | Fable 5.1 |
| #30 | Catalog MCP server in its own repository | #26, #23 | Opus |
| #31 | Skills query the MCP server with a file fallback | #30, #27 | Opus |
| #32 | Memory across runs (4) | #27 | Opus |
| #33 | Release v1.2.0, first remote consumer, `builder-p5` (5) | all | Sonnet |
| #38 | Walk-on-k3d rehearsal harness (GitOps source, Sealed Secrets, controller key); blocks the deploy criterion of #24 and #25 | — | Opus |

**#21 done (2026-10-31).** The nightly had been running on its schedule and was red on both days. support-copilot: the replay Job waited for the agent API but not for the orders stub, which only listens once Postgres accepts connections and was restarted by its liveness probe meanwhile, so lookups failed into false escalations; the baseline sits exactly at the 60 % threshold, so it passed or failed by timing. Fixed in the replay and, in the generator, with a startup probe on every health-checked workload. invoice-intake: G-SEC-6 found no Ingress on the runner and one locally against the same commit; `auth-check` now reads one row per document instead of `select` plus an alternative, which evaluates differently across yq 4.x (the root cause under yq 4.44.3 was not reproduced separately). Two manual runs on the branch were green.

| Per use case on `ubuntu-latest` | Runtime | Peak disk above start |
|---|---|---|
| invoice-intake | 4m30s to 4m41s | 18.4 GiB |
| support-copilot | 2m26s to 2m53s | 10.8 GiB |
| Whole nightly (jobs in parallel) | about 5m | 18.4 GiB per job; the root volume held 60 GiB at start and 78 GiB at the peak |

No image, model or disk change was needed on the runner, so the issue's disk and image criterion is met with no workaround. Local k3d runs on a laptop with a warm Docker cache took 2m15s and 8m06s.

**Walk on a real cluster: what is missing (2026-10-31).** Both golden use cases build `stages/walk`, pass kubeconform and the `ci` gates, and Crawl runs on k3d in the nightly. No source records `stages/walk` applied to a cluster, so everything Walk adds (ArgoCD syncing it, Sealed Secrets decrypting, the identity chain, PSA admitting the exception namespaces) is untested. #24 and #25 each ask for "a deploy of `stages/walk` on k3d" but do not say how the cluster-level pieces get resolved; proving Walk needs:

1. **A cluster shaped like Walk.** The stage installs ArgoCD, Longhorn (3 replicas), MetalLB, Traefik, Prometheus and Grafana. A k3d cluster has no replicated storage and no LoadBalancer pool. The test needs a named *Walk-on-k3d* profile (local-path storage, a MetalLB pool taken from the Docker network, or Traefik behind a port-forward) written down as a deviation, not passed off as the homelab shape.
2. **A GitOps source that exists.** Each Application tracks `ssh://git@github.com/AItizate/forjate.git` at `v1.2.0`, a tag that does not exist (latest is `v1.1.0`; the release is #33). ArgoCD also needs repository credentials, today a placeholder `sealed-argocd-ssh-keys`. Options: a release-candidate tag cut from the PR branch plus a read-only deploy key (exercises the real path and keeps `argocd-revision-check` true), or a test-only patch to a branch or an in-cluster git (cheaper, but it bypasses the control the gate guards). Prefer the rc tag.
3. **Sealed Secrets sealed for the test cluster.** Every `sealed-*.yaml` is a placeholder; a real one needs the target controller's public certificate, so the controller must be installed first, then `kubeseal`, then commit to the tag ArgoCD tracks. `scripts/convert-to-sealed-secret.sh` lists `k8s/overlays/*`, not `usecases/*`, so check it before relying on it. Real values never enter the repo: seal throwaway values at test time on the rc branch only.
4. **The controller key (G-OPS-1).** The gate is manual (devops signs) and says: back the controller key up offsite, encrypted, restore it into a scratch k3d and decrypt a test SealedSecret. The same harness can automate the restore half, with a fixed scratch key loaded before the controller starts, so sealing in step 3 and the key rehearsal are one mechanism. The offsite backup stays a human step.
5. **Workload images.** The Walk workloads from #24 and #25 must be built and pushed (`sync-app-image.yml`) and referenced by the stage; the registry needs a pull secret if the packages are private.
6. **Doubles for what is real at Walk.** invoice-intake reads a real IMAP mailbox and writes to Odoo; support-copilot uses Telegram (#25 already asks for a double) and a Cloudflare tunnel. None of these can be real in CI, so the harness patches them to doubles or drops the tunnel, and says so in the report.
7. **A hostname without public DNS or ACME.** The Ingress uses `letsencrypt-prod` and an `*.example.com` host. The test goes through a port-forward or a `nip.io` host with a self-signed issuer, and checks the auth chain with a test GoTrue user.

Done means: every Application `Synced` and `Healthy`; no Pod rejected by PSA (this is the first real test of the exception namespaces from #22); the Crawl verify Job passes against the Walk deployment; the review surface answers an unauthenticated request with a redirect or 401 and an authenticated one with 200; teardown leaves no cluster behind. Record runtime and peak disk as for the nightly.

**Decided 2026-10-31: #38.** A new issue, "Walk-on-k3d rehearsal harness", holds items 1 to 4 and 7: they are shared plumbing, written once, and would otherwise be built twice inside #24 and #25 with drift between them. #24 and #25 keep their scaffold work and consume the harness for their deploy criterion (items 5 and 6 stay per use case). The deploy criterion of each is blocked by the harness; the scaffold criteria are not. If the harness is judged too big for phase 5, the alternative is to narrow #24's criterion to the workload on the Crawl cluster and leave Walk-on-a-cluster explicitly out of the phase.

**#23 done (2026-10-29).** The catalog's `roles` became **capabilities** (the schema's `role` stays the expert's name; the two vocabularies were colliding): 36 needs in `wiki/catalog-capabilities.yaml` with `asked_by`, `exclusive` and `setting`, documented in `contracts.md` and kept equal by a test. Every curated component carries `gpu_required`, `ha`, `psa_restricted`, `secrets: {takes, mechanism, rank}` and `data_classes` (potential with configuration, not as shipped); Vault left the curated set (deprecated by OpenBao, which entered as `secrets-store`), so pairing OpenBao with External Secrets is no longer a conflict. `validate.py` names no component any more: the secrets ranking, the exclusive groups, the setting→component maps and the CDC-implies-broker rule are derived from `catalog.json` at run time, with a warning when none is reachable. `wiki-compile.py` validates capabilities against the vocabulary and writes `references/catalog-snapshot.md` for the nine skills that resolve components (declared once, in `asked_by` plus `snapshot_all`); `wiki-compile --check` in CI fails on a stale snapshot like on a stale catalog. Grader: `choice_has_capability`, `choice_lacks_capability`, `choice_capabilities()` in `yaml_expr`. `skill-lint.py` runs in `validate-builder.yml` in warn mode: 67 catalog paths named outside snapshots today (data-store 11, architecture 13, compliance 16, data-pipeline 10, ai-engineering 7, security 6, kustomize 3, devops 1; ux and devops mostly single-option), the inventory #27 works from. `backup` is a capability with no component until #6.


**#27 in progress (2026-10-30).** Every skill asks the catalog by capability and property: a `choice` is what `wiki/catalog.json` resolved for the capabilities the expert asks (`inference`, `llm-gateway`, the five memory capabilities, `durable-workflows`, `message-broker`, `secrets-mechanism` ranked by `secrets.rank`, ...), names stay in the generated snapshots and where a capability has one option, and `skill-lint.py --strict` runs in CI with zero findings (67 before). The governance posture of `context-packs/examples/enterprise-in-a-box` and `docs/agentic-reference-architecture.md` lives in the skills as settings every expert emits by default (`contracts.md`, "Governance settings", 22 keys with one owner each: `autonomy`, `write_actions`, `execution_bounds`, `intent_validation`, `kill_switch`, `model_pinning`, `fallback_policy`, `semantic_memory_strategy`, `memory_scopes`, `scope_isolation`, `audit_artifacts`, `eval_dimensions`, `open_standards`, `review_mode`, `review_independence`, `control_levels`, `disclosure`, `raci`, `operating_model`, `adoption_frictions`, `severities`, `model_register`), each in a `## Governance posture` section with the rule and its reason; a pack only tightens a value (`require_setting` / `deny_setting_value`, so EXE-2 and AUT-2 became deny rules), and a test keeps the table, the skills and the pack equal. Decided with the user before writing: the format (section + the pack's own target names), the vocabulary in `contracts.md` with a test, the seven evaluation dimensions as a floor every expert contributes to and quality consolidates (`quality/references/eval-dimensions.md`), and `autonomy` per stage in the stage-plan schema (check 10: Crawl assistive, no stage above the brief, no record above the plan). The brief fields `autonomy`, `risk_profile`, `isolation` and `open_standards_required` are read by the planner, ai-engineering, ux, data-store, security, architecture and the coordinator's intake.

The #22 debt is paid: `assemble.py` has no component table. `wiki-compile.py` derives `wiring` per component from its manifests (Service and port, pod label, the Secret the pods reference and the keys its examples document, shipped placeholders, a ConfigMap to generate, an Ingress, a GPU limit, hostPath volumes) and `catalog-overrides.yaml` curates only what the tree cannot say (the protocol, laptop sizing, the Secret a bare Pod takes but never references, the Service of a bundle); a curated value the tree contradicts is a compile error. Replacing a component (MinIO is deprecated) is one overrides entry plus its manifests, no script edit. Stage overlays are built from each stage's own set (`common.stage_components`, shared by validate check 9 and the assembly): a Crawl component no Walk record repeats leaves through a `$patch: delete` in `relocated/` with its Secret (the MinIO dev Pod at Walk, Ollama at Walk in support-copilot and at Run in invoice-intake), and check 11 warns when nothing covers its capability and no rationale says so. Golden overlays regenerated and byte-checked; the derivation also fixed stale table entries (the IdP pod label, the gateway's two secret keys, a placeholder delete that matched nothing).

Evals on Opus, every suite re-run, assertions on names converted to `choice_has_capability` and one judgement assertion per posture rule, a pack eval under `enterprise-in-a-box` for ai-engineering. With skill / without, every with-skill suite at or above its previous benchmark: ai-engineering 100 / 80, business 100 / 81, architecture 100 / 83, data-store 100 / 83, data-pipeline 100 / 69, security 100 / 75, compliance 100 / 79, quality 100 / 76, devops 100 / 78, stage-planner 100 / 98, coordinator 100 / 89, ux 100 / 66, app-scaffold 100 / 88, <kustomize: pending>. Two skills regressed on the first pass and the cause was terseness, as the agreement predicted: security and compliance copied `intent_validation`, `scope_isolation`, `model_pinning`, `audit_artifacts` and `open_standards` from records that predate the posture (the fixtures) and left the keys out when the owner was silent; both now write the factory floor as a setting and ask the owner to confirm. Every other with-skill miss was the assertion's fault, in the shapes section 3 lists: an exact match on a value with a suffix (`0% (from the brief)`), an uppercase pattern in a lowercased grep, a path pointing at the other use case, a word hunted in the risk's `text` when it sat in `mitigation`, a fixed shape where the record argued soundly for another (a synthetic replay when the data class forbids real transcripts, the gateway key as the Run kill switch when the worker never passes the ingress, a Run cost above the envelope with a blocking question for the business expert), and one eval written before the expert agents existed (the coordinator's resume listed every expert as not yet available; it now scopes the run to wave 1). Baselines are high where the schema and the prompt carry the shape (stage-planner, app-scaffold, the `pack-enterprise-posture` eval passes without the skill because the pack names the settings); the quality metrics (alternatives, risks, automated gates) are where the skill shows there. Benchmarks in `benchmarks/*-2026-10-30.md` and `*-2026-10-31.md`; `experts.md` lists the capabilities and the posture per expert.

**#22 done (2026-10-29).** The use case's namespace enforces the stage's `psa_level` (Walk `baseline` with `restricted` as warn and audit, Run `restricted`, a pack can raise Walk) and nothing lowers it. Whatever runs below it is an entry of the security record's new stage-level `psa_exceptions` (`namespace`, `level`, `components`, `owner`, `reason`, `risk`): a `risks` entry alone was not enough, because the assembly has to act on it and the validator has to check it. Decision by the user in the session: no validator or script names a component, since the catalog will grow and components change namespace. So `wiki-compile.py` now derives two facts per component from `k8s/**`: `psa_level` (from the pod templates: host access is `privileged`, the restricted profile on every container is `restricted`) and `namespace` with `namespace_how` (`declares`, `remote`, `sets`, `none`, from the kustomization, the manifests and Helm charts). Overrides cover only remote manifests, plus a `null` for the two MinIO components that pin a namespace but belong in the use case's. An override the tree contradicts is a compile error. `validate.py` check 9 and `assemble.py` read the facts and name no component: the assembly's infra prefixes became the catalog's `namespace`, and the CDC prefix became the `cdc` capability.

From Walk, the assembly labels every shared namespace at the level its pods meet (Kubernetes' own namespaces never). It moves the use-case-scoped exceptions to `uc-<name>-baseline` with a relocation layer, ExternalName aliases, per-namespace Secrets and default-deny, and the auth middleware follows the identity provider; the tenant target writes the same as namespace children. A test regenerates both golden overlays and fails on drift. `psa-check` reads the exception namespaces too. invoice-intake (pack SEC-1, `restricted` at Walk) now runs only its own workloads in `uc-invoice-intake`, with the catalog components in `uc-invoice-intake-baseline`. support-copilot's tunnel Secret moved to `cloudflare-tunnel`, where cloudflared can read it.

Security suite on Opus (`benchmarks/security-2026-10-29.md`): with skill 100%, without 90% (2026-10-03: 98% / 73%). The new assertion passed in both configurations: the schema's description of `psa_exceptions` and the catalog facts carry the rule even without the skill, so it guards the contract rather than discriminating. Found on the way, left for #27: stage overlays keep every Crawl component at Walk (the MinIO dev Pod, support-copilot's Ollama), and `assemble.py` still holds the per-component wiring table (`COMPONENTS`: service, port, secret, sizing), the last hardcoded component list in the builder's scripts.
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
| 4 UX + assembly | 1.5 (done in 2 days) | `builder-p4` |
| 5 Hardening + protocol | 2 | `builder-p5` / `v1.x.0` |

Total ≈ 10.5 weeks of focused work; phases 2 and 3 parallelize across people if available.

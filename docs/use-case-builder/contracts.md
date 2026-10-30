# Use-case builder contracts

Everything the builder team produces is YAML validated against a JSON Schema in `plugins/forjate/scripts/builder/schemas/`. The artifacts live under `k8s/overlays/usecases/<name>/.builder/` and are the review surface: a stakeholder reads them, CI validates them, the next expert consumes them.

| Artifact | Schema | Written by | Read by |
|----------|--------|------------|---------|
| `.builder/brief.yaml` | `brief.schema.json` | `forjate:coordinator` (intake), enriched by `forjate:business` | everyone |
| `.builder/packs.yaml` | `packs-active.schema.json` | `forjate:coordinator` | `packs.py resolve` |
| `.builder/stage-plan.yaml` | `stage-plan.schema.json` | `forjate:stage-planner` | coordinator, every expert |
| `.builder/decisions/<area>.yaml` | `decision.schema.json` | the expert for that area | coordinator, `forjate:kustomize`, `forjate:quality`, reviewers; `business.yaml` is read by every other expert |
| `.builder/gates.yaml` | `gates.schema.json` | `forjate:quality` | coordinator, approvers |
| `usecase.yaml` | `scripts/ephemeral/usecase.schema.json` | `forjate:kustomize` | `ephemeral.sh`, agents |
| `context-packs/<name>/pack.yaml` | `pack.schema.json` | pack authors | `packs.py` |
| `context-packs/<name>/constraints.yaml` | `constraints.schema.json` | pack authors | `packs.py`, `validate.py` |

Shared vocabulary (`_defs.schema.json`): stages are `crawl`, `walk`, `run`; the schema's `role` is an **expert**, one of the plugin's skill names (`forjate:data-store`); components are paths relative to `k8s/components/`; a rule reference is `pack:<name>#<ID>`; data classes are `none`, `internal`, `pii`, `financial`, `health`, `secret`. What a component is *for* is a **catalog capability**, a different vocabulary, below.

## Catalog capabilities

Experts do not choose components by name; they ask the catalog for a **capability** and resolve it at run time from `wiki/catalog.json`, applying the selection criteria to the candidates and recording the rejected ones in `alternatives`. The vocabulary lives in `wiki/catalog-capabilities.yaml` (the compiler rejects a component tagged with a capability that file does not define); `wiki/catalog-overrides.yaml` tags every curated component with the capabilities it covers and the properties the criteria need. A test keeps this table and the YAML equal.

A capability is a need, not a product category. "Postgres with a TTL column can hold session memory at Crawl when a second store is not worth it" is a rule of judgement that belongs in the data-store skill; `session-memory` is the capability, and today Redis is its only option.

| Capability | Asked by | One per stage | Setting | What it is for |
|------------|----------|---------------|---------|----------------|
| `session-memory` | data-store | | | short-lived context with a TTL; rate limits and locks |
| `working-memory` | data-store | | | transactional state the agent must not lose |
| `episodic-memory` | data-store | | | structured history of what happened |
| `semantic-memory` | data-store | yes | | embeddings for retrieval over unstructured text |
| `artifact-store` | data-store | yes | | documents, prompts, logs and reports as objects |
| `cache` | data-store, architecture | | | hot data in front of a slower store |
| `coordination` | architecture | | | leader election, locks, shared configuration |
| `inference` | ai-engineering | yes | `inference` | serves a model in the cluster; zero egress |
| `llm-gateway` | ai-engineering | | | one endpoint in front of local and external models; routing, budgets, egress policy |
| `chat-ui` | ux | | | a human-facing chat surface |
| `feedback` | ux | | | in-product feedback capture |
| `message-broker` | architecture, data-pipeline | yes | `broker` | decouples workloads, fans out events |
| `mqtt-broker` | architecture, data-pipeline | | | pub/sub for devices |
| `durable-workflows` | architecture | | | multi-step work that survives a pod dying |
| `cdc` | data-pipeline, architecture | | | a database's change log published to a broker |
| `document-parsing` | data-pipeline | | | PDF and Office to structured text |
| `identity-provider` | architecture, security | | | who the user is, for oauth2-proxy |
| `public-ingress` | architecture, devops | | | reachable from the internet without an open port |
| `low-code-automation` | architecture | | | visual flows for glue |
| `secrets-mechanism` | security, devops | yes | `secrets_mechanism` | how a secret reaches a workload; ranked, floor `secret-generator` |
| `secrets-store` | security | | | where secrets live; audit, rotation, short-lived credentials |
| `access-control` | security | | | service accounts and RBAC |
| `gitops` | devops | | | the cluster converges on git |
| `block-storage` | devops | | | replicated persistent volumes |
| `static-storage` | kustomize | | | pre-provisioned volumes for a lab cluster |
| `load-balancer` | devops | | | LoadBalancer services on bare metal |
| `metrics` | devops | | | time series; the source of metric gates |
| `dashboards` | devops | | | operational dashboards and alerting |
| `telemetry` | devops | | | logs and traces, including model and tool calls |
| `config-reload` | devops | | | restart consumers on config change |
| `cluster-ui` | devops | | | a web view of the cluster |
| `image-registry` | devops | | | images close to the cluster |
| `backup` | devops | | | scheduled backups and rehearsed restores (no component today) |
| `cloud-resources` | devops | | | managed cloud services from Kubernetes objects |
| `bi` | devops | | | business dashboards over the system of record |
| `smoke-test` | kustomize | | | proves ingress, TLS and routing |

**Exclusive** capabilities ("one per stage") are the groups `validate.py` check 6 reads: two records that choose two components of one exclusive capability for the same stage are in conflict, and the capability's **setting** names the record key whose value picks one of them (`broker: nats` and a choice of `apps/brokers/rabbitmq` is the same conflict). `secrets-mechanism` carries the ranking check 4 uses for `secrets_mechanism` rules: each component with that capability declares `secrets.mechanism` and `secrets.rank`, and the vocabulary declares the floor without a component (`secret-generator`, rank 0). Nothing in the validator names a component.

### Component properties

Every curated component in `wiki/catalog-overrides.yaml` carries, besides `capabilities`:

| Property | Values | What an expert does with it |
|----------|--------|-----------------------------|
| `stages` | `crawl`, `walk`, `run` | fitness; `[]` means in the tree but never chosen |
| `maturity` | `lab`, `mvp`, `production` | how battle-tested in this factory |
| `gpu_required` | `required`, `optional`, `none`, `unknown` | exclude `required` when no GPU node exists; `optional` is a Walk latency question |
| `ha` | `single`, `replicated`, `operator`, `n/a`, `unknown` | as deployed: `single` loses data with the node, `operator` makes HA a config change |
| `psa_restricted` | `true`, `false`, `n/a`, `unknown` | whether the shipped manifests run under `restricted`; `false` is a recorded exception in its own namespace (#22) |
| `psa_level` | `privileged`, `baseline`, `restricted`, `n/a`, `unknown` | **derived** by `wiki-compile.py` from the pod templates (host access is `privileged`, the restricted profile on every container is `restricted`), curated only where the manifests are remote or Helm; the strictest level the component's pods meet. Below the stage's `psa_level` it is a PSA exception, never a reason to lower the use case's namespace |
| `namespace`, `namespace_how` | a namespace or `null`; `declares`, `remote`, `sets`, `none` | **derived** from the kustomization's `namespace:`, the manifests and Helm charts, curated for remote manifests or set to `null` for a component whose manifests pin a namespace but that belongs in the use case's. A component with a `namespace` is shared infrastructure: it runs there, at its own level. `namespace_how` tells the assembly whether to label the Namespace (`declares`, `remote`), declare it (`sets`) or place the component in it (`none`). An override the tree contradicts is a compile error |
| `secrets` | `takes`: `none`, `env`, `sealed`, `unknown`; `mechanism`, `rank` on secrets-mechanism components | what the overlay must supply; the ladder |
| `data_classes` | subset of `internal`, `pii`, `financial`, `health`, `secret`; `[]` touches no use-case data | what the component can hold or transit when configured for it; the brief's classification must be in the list (or `none`) |
| `licence`, `notes` | free text | for compliance; one line for the experts |

Selection order when several candidates remain: stage fitness, pack rules (`deny_components`, `allow_components_only`), data classes against the brief, GPU against the environment, HA against the stage's exit criteria, maturity, licence. Record the rejected candidates in `alternatives` with the criterion that excluded them.

### Snapshots

`scripts/wiki-compile.py` writes `plugins/forjate/skills/<skill>/references/catalog-snapshot.md` for every skill that resolves components: the skills named in any capability's `asked_by`, plus `snapshot_all` (kustomize and compliance, which consume the whole catalog). Which skill sees which capability is declared there and nowhere else. A snapshot shows what the catalog resolved on a date and says so; it is never a rule. Prose in a skill may name a component only when it is the single option for one of its capabilities; `plugins/forjate/scripts/builder/skill-lint.py` flags every other catalog path outside the snapshots. Evals assert capabilities with `choice_has_capability` / `choice_lacks_capability`, names only for single-option capabilities.

## Decision record

The one shape every expert returns. Per stage: what was chosen (`choice`, catalog components), structured values other tools look at (`settings`), why (`rationale`), what was rejected (`alternatives`), `risks`, the `gate_to_next` conditions, and the pack rules that shaped it (`constrained_by`). Outside the stages: `open_questions` only the user can answer, and `references`.

`settings` is deliberately flat (scalars or lists of scalars) so pack rules can be matched mechanically. The keys the validator knows about today:

| key | emitted by | matched by rule type |
|-----|------------|----------------------|
| `psa_level` | security, devops | `min_psa_level`; cross-record consistency (check 6) |
| `secrets_mechanism` | security, devops | `secrets_mechanism`; cross-record consistency (check 6), also against the secrets component another record chose |
| `model` | ai-engineering | `model_allowlist`, `model_denylist` |
| `data_egress` | ai-engineering, security, compliance | `data_egress`; cross-record consistency (check 6) |
| `data_residency` | data-store, compliance, devops | `data_residency`; cross-record consistency (check 6) |
| `namespace` | kustomize, devops | `naming_pattern` (target `namespace`) |
| `broker` | architecture, data-pipeline | cross-record consistency (check 6) |
| `inference` | ai-engineering | cross-record consistency (check 6) |
| `network_policy` | security, devops | cross-record consistency (check 6) |
| `backup` | data-store, devops | cross-record consistency (check 6) |
| `auth_in_front` | architecture, security, ux | cross-record consistency (check 6) |
| `judge`, `kpi_metric_source`, `regression_trigger` | quality | `require_setting`, `deny_setting_value` |
| `surface`, `feedback_capture` | ux | `deny_setting_value` (with `target`) |
| `autonomy` | ai-engineering, ux, quality (from the plan's ceiling) | check 10 (never above the plan); cross-record consistency (check 6) |
| `write_actions`, `intent_validation`, `kill_switch`, `model_pinning`, `fallback_policy`, `audit_artifacts`, `open_standards`, `scope_isolation` | the owner and the experts a pack rule applies to ("Governance settings") | cross-record consistency (check 6); `require_setting`, `deny_setting_value` |
| any key | any | `require_setting`, `deny_setting_value` (with `target`) |

The full key set each expert emits is documented in `experts.md`.

### PSA exceptions

The security record's stage may carry `psa_exceptions`, a list of namespaces below the stage's `psa_level` that run components of the use case. Each entry has `namespace`, `level` (`privileged` or `baseline`), `components` (catalog paths), `owner` (who sets and accepts the level) and `reason` (the catalog fact or the host access), plus an optional `risk` id carrying severity and mitigation. A `risks` entry alone is not enough: the assembly has to act on the exception (label the namespace, move the components there) and the validator has to check it against the catalog, and neither can read prose. Two kinds of entry:

- **Shared infrastructure** (a component whose catalog `namespace` is set) already runs in its own namespace; the entry records that this namespace runs below the use case's level and who owns it.
- **A use-case-scoped component the catalog does not prove at the stage's level** moves to a namespace of the use case's own (convention `uc-<name>-<level>`); the assembly relocates it and leaves an ExternalName alias of each of its Services in `uc-<name>`, so no consumer changes.

The use case's own namespace is never an exception and never lowered.

Plus `estimated_cost_usd_month` at stage level, matched by `max_cost_usd_month`.

### Governance settings

The posture an enterprise expects of an agentic system (bounded execution, intent validation before a write, a kill switch, memory with a scope, audit artifacts per action, review that validates, an operating model) is written into the records as **settings every expert emits by default**, so it holds without a pack; a context pack only tightens the value with `require_setting` / `deny_setting_value` (`context-packs/examples/enterprise-in-a-box` is the reference pack and uses exactly these keys). Each skill documents the keys it owns in its `## Governance posture` section, with the rule and its reason; this table is the vocabulary, and a test keeps the table, the skills and the pack equal. A key has one **owner**; the experts a pack rule `applies_to` copy the owner's value (check 6 treats a silent difference as a conflict, like `psa_level`). Values are closed enums or lists of `<name>: <text>` lines, so the validator can match them.

| key | values | owner | copied by | default Crawl → Walk → Run | pack rule |
|-----|--------|-------|-----------|-----------------------------|-----------|
| `autonomy` | `assistive` / `semi-autonomous` / `autonomous` | stage-planner (plan `stages.<s>.autonomy`) | ai-engineering, ux, quality | `assistive` → ≤ `semi-autonomous` → ≤ the brief's `autonomy` | AUT-1 (`require_setting`) |
| `write_actions` | `none` / `approval-required` / `registered-tools-only` / `autonomous` | ai-engineering | security, quality | `none` → `approval-required` → `registered-tools-only`, `autonomous` only per action with a gate | AUT-2 |
| `execution_bounds` | list `max_steps=<n>`, `step_timeout_s=<n>`, `delegation_depth=<n>`, `budget_tokens=<n>` | ai-engineering | architecture, quality | set at every stage; Crawl may be generous, never absent | EXE-1 |
| `intent_validation` | `disabled` / `schema` / `policy-judge` | ai-engineering | security | `schema` → `policy-judge` when any tool writes → `policy-judge` | EXE-2 (`deny_setting_value: [disabled]`) |
| `kill_switch` | `none` / `gateway-key-revocation` / `ingress-permission` | security | ai-engineering, devops | `none` → `gateway-key-revocation` → `ingress-permission`, rehearsed (`G-SEC-<n>`) | EXE-3 (via `auth_in_front`) |
| `model_pinning` | `pinned` / `floating` | ai-engineering | compliance | `pinned` at every stage | MOD-1 |
| `fallback_policy` | `none` / `same-tier` / `lower-tier` / `any` | ai-engineering | security | `none` → `same-tier` → `same-tier` | MOD-2 (`deny_setting_value: [lower-tier, any]`) |
| `semantic_memory_strategy` | `none` / `api-lookup` / `runtime-retrieval` / `compiled-knowledge` (list allowed) | ai-engineering | data-store | `api-lookup` when the facts live in an API or a table; `runtime-retrieval` or `compiled-knowledge` only with a corpus | — |
| `memory_scopes` | list `<kind>: <scope>`, scope in `session` / `user` / `project` / `org` | data-store | ai-engineering | every kind in `memory_kinds` has a scope at every stage | MEM-1 |
| `scope_isolation` | `key-prefix` / `schema-per-tenant` / `database-per-tenant` / `cluster-per-tenant` | data-store | security, devops | `key-prefix` → the floor the brief's `isolation` implies (`logical` ≥ `schema-per-tenant`, `physical` = `cluster-per-tenant`) | — |
| `audit_artifacts` | `none` / `run-trace` / `per-action` | quality | compliance, ai-engineering, devops | `run-trace` → `per-action` (a gate) → `per-action` | AUD-1 |
| `eval_dimensions` | list `<dimension>: <how measured>`; the seven factory dimensions are the floor | quality (consolidates) | any expert may contribute lines | the seven at every stage a model is in the loop | — |
| `open_standards` | `all-layers` / `partial` / `n-a`; exceptions in `open_standards_exceptions` | architecture | devops, compliance | `all-layers` when the brief sets `open_standards_required`; otherwise `partial` with the exceptions named | STD-1 |
| `review_mode` | `evidence-first` / `verdict-only` / `n-a` | ux | quality | `evidence-first` wherever a checkpoint exists | REVIEW |
| `review_independence` | `independent` / `sequential` / `n-a` | ux | — | `independent` where the decision is regulated or irreversible (`risk_profile`) | REVIEW |
| `control_levels` | list `<persona>: direct\|approve\|audit\|operate` | ux | security | one line per human actor from Walk | REVIEW |
| `disclosure` | list `<point>: <what the user is told>`, or `none` with the reason | ux | — | required from Walk when the surface is `customer-facing` | REVIEW |
| `raci` | list `<activity>: R=<role> A=<role>` | business | coordinator (report) | the four activities (agent design, operation and review, integration, risk and audit) | OPMODEL |
| `operating_model` | `co-delivery` / `internal` / `vendor-delivered` | business | — | `co-delivery` unless the brief says the organisation builds alone | OPMODEL |
| `adoption_frictions` | list `<friction>: <owner>, <mitigation>` for data readiness, Infosec approval, change management | business | — | the three, each with an owner, mirrored in `risks` | OPMODEL |
| `severities` | list `S1: ...` to `S4: ...`, S1 with on-call | devops | — | from Walk | OPMODEL |
| `model_register` | `none` / `in-record` / `org-register:<ref>` | compliance | — | `in-record` → `in-record` → `org-register:<ref>` or an open question | MODELGOV |

The seven factory evaluation dimensions, and which expert measures each, are in `plugins/forjate/skills/quality/references/eval-dimensions.md`.

## What `validate.py` checks

1. Schema validity of every artifact.
2. Every component in a `choice` exists under `k8s/components/`.
3. Every `pack:<name>#<ID>` cited exists in an active pack.
4. No stage decision violates a `must` of a structured type that applies to its area, its stage and the brief's data classification. `secrets_mechanism` rules are ranked through the catalog (`secrets.rank` of the secrets-mechanism components); without a reachable `wiki/catalog.json` the ranking and check 6's groups are skipped with a warning (`FORJATE_ROOT` points at a factory checkout).
5. Plan/decision consistency: experts the plan runs have a record (warning), decisions do not cover skipped stages (warning).
6. Cross-record consistency: for each stage, two records that choose components of one exclusive catalog capability (`message-broker`, `semantic-memory`, `inference`, `artifact-store`, `secrets-mechanism`, read from `wiki/catalog.json`), that imply one through the capability's setting (`broker`, `inference`, `secrets_mechanism`) or a CDC connector's suffix, or that disagree on a shared setting (`psa_level`, `secrets_mechanism`, `data_residency`, `data_egress`, `network_policy`, `backup`, `auth_in_front`) are a **conflict**. So are two records that claim one gate id (`gate_to_next[].id`) with different texts. A conflict is an error unless some record carries an open question naming both sides, in which case it is a warning the coordinator reports to the user. The validator never resolves a conflict and the coordinator never edits a record to make one disappear.
7. Gates consolidation: when `gates.yaml` exists, every gate id a record emits in `gate_to_next` for a stage with a transition out of it appears under that transition (warning otherwise), and every `pack_overrides.rule` exists in an active pack (error otherwise).
8. `ci` gate refs: a gate whose `check.type` is `ci` names a script in `scripts/gates/checks/` (the directory is the enum the gates runner executes). An unknown ref is an error in `gates.yaml` and a warning in a record's `gate_to_next`; when no checks directory is reachable (a tenant repo without the factory checked out) the check is skipped with a warning and `FORJATE_ROOT` points the validator at one.

9. PSA exceptions: an entry in `psa_exceptions` that names the use case's namespace or a component outside the catalog is an error; one at or above the stage's level, or listing a component no record runs at that stage, or putting a shared component in another namespace than the catalog's, is a warning. Every component a stage runs (the records' choices **at that stage**, the set the assembly builds the stage overlay from; see 11) whose catalog `psa_level` is below the stage's `psa_level` and that no entry covers is a warning, grouped per shared namespace or listed as would-run-in-`uc-<name>`. Where a component runs and the level it meets come from `wiki/catalog.json`; the validator names no component.
10. Autonomy: the plan's Crawl `autonomy` is `assistive`; no stage's ceiling exceeds the brief's `autonomy`; no record's `settings.autonomy` exceeds the plan's ceiling for its stage. Errors: a wrong ceiling is a wrong contract.
11. Supersede: a component some record chose at one stage and no record chooses at the next is superseded by a component of the same capability at that stage, or dropped on purpose; when neither a same-capability replacement exists nor a rationale at that stage names it, a warning says the stage overlay drops it. Stage overlays are built from each stage's own set (`common.stage_components`, shared by the validator and the assembly): a Crawl-only component (a dev object store, a CPU inference server) leaves the build at Walk through a `$patch: delete` in the stage's relocation layer, and its Secret leaves with it.

Warnings never fail CI; errors do.

## Lifecycle of the artifacts

```
intake ──► brief.yaml + packs.yaml
   │
   ▼
planner ─► stage-plan.yaml
   │
   ▼
experts ─► decisions/*.yaml   (business first, then the rest in parallel)
   │
   ▼
quality ─► gates.yaml          (consolidate mode: every gate_to_next verbatim, a check per gate, pack overrides)
   │
   ▼
kustomize ► usecase.yaml, kustomization.yaml, stages/walk, stages/run
   │
   ▼
ephemeral.sh up <name>         (Crawl proven on a cluster)
```

Every arrow is a point where a human can stop and review, because every arrow is a file in git.

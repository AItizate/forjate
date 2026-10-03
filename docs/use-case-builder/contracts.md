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

Shared vocabulary (`_defs.schema.json`): stages are `crawl`, `walk`, `run`; roles are the plugin's skill names; components are paths relative to `k8s/components/`; a rule reference is `pack:<name>#<ID>`; data classes are `none`, `internal`, `pii`, `financial`, `health`, `secret`.

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
| `auth_in_front` | architecture, security | cross-record consistency (check 6) |
| `judge`, `kpi_metric_source`, `regression_trigger` | quality | `require_setting`, `deny_setting_value` |
| any key | any | `require_setting`, `deny_setting_value` (with `target`) |

The full key set each expert emits is documented in `experts.md`.

Plus `estimated_cost_usd_month` at stage level, matched by `max_cost_usd_month`.

## What `validate.py` checks

1. Schema validity of every artifact.
2. Every component in a `choice` exists under `k8s/components/`.
3. Every `pack:<name>#<ID>` cited exists in an active pack.
4. No stage decision violates a `must` of a structured type that applies to its area, its stage and the brief's data classification.
5. Plan/decision consistency: experts the plan runs have a record (warning), decisions do not cover skipped stages (warning).
6. Cross-record consistency: for each stage, two records that choose components from one exclusive group (brokers `nats`/`rabbitmq`, vector stores `lancedb`/`milvus`, inference `ollama`/`vllm`, object storage `minio/dev`/`minio/single-server`, secrets `sealed-secrets`/`external-secrets`/`vault`), that imply one through a setting (`broker`, `inference`, `secrets_mechanism`) or a CDC connector's suffix, or that disagree on a shared setting (`psa_level`, `secrets_mechanism`, `data_residency`, `data_egress`, `network_policy`, `backup`, `auth_in_front`) are a **conflict**. So are two records that claim one gate id (`gate_to_next[].id`) with different texts. A conflict is an error unless some record carries an open question naming both sides, in which case it is a warning the coordinator reports to the user. The validator never resolves a conflict and the coordinator never edits a record to make one disappear.
7. Gates consolidation: when `gates.yaml` exists, every gate id a record emits in `gate_to_next` for a stage with a transition out of it appears under that transition (warning otherwise), and every `pack_overrides.rule` exists in an active pack (error otherwise).

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

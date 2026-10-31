# Kind → capability → component, per stage

A memory kind names a **capability** the catalog resolves; you pick among the candidates by their properties, never by habit. Read `wiki/catalog.json` (`stages`, `ha`, `gpu_required`, `data_classes`, `maturity`, `licence`, `notes`); `catalog-snapshot.md` shows what each capability resolved to on the compile date. Selection order when several candidates remain: stage fitness, pack rules, data classes against the brief, HA against the stage's exit criteria, maturity, licence. Every rejected candidate goes in `alternatives` with the criterion that excluded it.

| Kind | Capability | Crawl | Walk | Run | What decides between candidates |
|------|------------|-------|------|-----|---------------------------------|
| `session` | `session-memory` | the candidate fit for `crawl`, or the relational `working-memory` store with a TTL column when a second store is not worth it for a PoC (say so, name the split at Walk) | the `session-memory` candidate | the same with persistence, or a managed compatible service within the residency rule | TTL and eviction support; the licence note on the image tag; rate limiting and locks live here too |
| `working` | `working-memory` | the relational candidate fit for `crawl` | the same | the same via its operator when `ha: operator` is available, for HA and PITR | transactional guarantees: idempotency keys, cursors and approval status are never in a cache past Crawl (a lost cursor re-reads the mailbox) |
| `episodic` | `episodic-memory` | the relational candidate (a JSON column for the variable parts) | the relational candidate; a document-shaped candidate only for genuinely document-shaped chat state with the licence accepted | the relational candidate via its operator | licence (`SSPL` and source-available candidates are flags for compliance and often denied by a pack); when the default relational candidate is denied, the other relational candidate is the alternative, not the document store |
| `semantic` | `semantic-memory` | the single-writer candidate fit for `crawl` | the same | the candidate fit for `run` when the single-writer model is the bottleneck | only when the AI-engineering record's `semantic_memory_strategy` is `runtime-retrieval` or `compiled-knowledge`; `ha` and the dependencies the notes list (a coordination store, an object store) |
| `artifacts` | `artifact-store` | the candidate fit for `crawl` only (a dev convenience, superseded at Walk) | the candidate fit for `walk` (operated, restricted-compatible) | the same via its operator, or an S3-compatible service within residency | `stages` and `psa_level`: the Crawl candidate leaves the build at Walk; buckets per kind (`inbox`, `parsed`, `audit`, `seed`), object keys carry the idempotency key |

## Default shapes

**Chat agent (support copilot)**: `session` → the `session-memory` store (scope `session`); `working` and `episodic` → the relational store (scopes `user`); no `semantic` (the orders API is the lookup: `api-lookup`); `artifacts` only if transcripts must be exported for audit. Crawl may keep session in the relational store and say so.

**Document intake (invoices)**: `artifacts` → the artifact store (inbox, parsed, audit; scope `project`); `working` → the relational store (mailbox cursor, approval status; `project`); `episodic` → the relational store (extraction per invoice, decisions; `project`); no `session`; no `semantic` unless matching needs free-text retrieval across past invoices.

**Migration**: `working` → the relational store (progress, checkpoints; a cache is acceptable for a checkpoint store if a restart from zero is cheap); `artifacts` → the artifact store (verification report). Nothing else.

## Secrets the stores need

Catalog stores expect the overlay to supply a Secret whose name and keys the catalog's `wiring` facts carry (`secrets.takes: env`); the kustomize skill writes the `.env.example`. Your record names the stores; it does not carry credentials.

## Sizing hints for `risks`

A single-replica relational StatefulSet (`ha: single`): fine to tens of GB and hundreds of writes per second; the operator at Run is for HA, not for size. A cache: memory-bound; name the eviction policy. A single-writer vector store: concurrent ingestion is the limit. A single-server object store (`ha: single`): no redundancy; the Run gate is the operated tenant.

## `storageClassName` is an overlay parameter

Observed in a production tenant: one global patch targeting every PVC plus a `volumeClaimTemplates/0` patch per StatefulSet, because catalog components either omit the class (k3d default `local-path` at Crawl) or hard-code one. Your record names the class per stage (`local-path` at Crawl, the `block-storage` component's class from Walk, as the devops record's `storage_class`) in `rationale`; the kustomize skill writes:

```yaml
patches:
  - target: { kind: PersistentVolumeClaim }
    patch: |
      - op: add
        path: /spec/storageClassName
        value: longhorn
  - path: patches/<store>-storage-patch.yaml          # /spec/volumeClaimTemplates/0/spec/storageClassName
    target: { kind: StatefulSet, name: <store> }
```

## Init Jobs for a shared relational or document store

When several workloads share one database server (the tenant pattern: one StatefulSet, many databases), name it in `rationale` as the `multi-database init` pattern so the kustomize skill ships it: an env listing the databases on the StatefulSet with an init script, or an init script through a `configMapGenerator` with `disableNameSuffixHash: true`, applied by an `<app>-init-job.yaml` with `ttlSecondsAfterFinished` and `backoffLimit`. Those Jobs assert nothing; the verify Job does. One database per workload, credentials per database in their own Secret, one schema or database per tenant when `scope_isolation` is `schema-per-tenant` or `database-per-tenant`, and the system-of-record rule still applies: none of them is a copy of the ERP.

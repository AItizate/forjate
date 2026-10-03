# Components per kind and stage

Catalog paths relative to `k8s/components/`. Check `wiki/catalog.json` `stages`, `roles` and `notes` before choosing; the notes carry the licence caveats.

| Kind | Crawl | Walk | Run | Notes |
|------|-------|------|-----|-------|
| `session` | `apps/databases/redis`, or Postgres with a TTL column when adding Redis is not worth a second store for a PoC | `apps/databases/redis` | Redis with persistence, or a managed Redis-compatible service through the residency rule | Redis 7.4+ changed licence; the catalog note says to check the image tag. Rate limiting and locks live here too. |
| `working` | `apps/databases/postgres` | `apps/databases/postgres` | Postgres via operator (CNPG) for HA and PITR | Idempotency keys, cursors, approval status. Never in Redis past Crawl: a lost cursor re-reads the mailbox. |
| `episodic` | `apps/databases/postgres` (JSONB for the variable parts) | Postgres; `apps/databases/mongodb` only for genuinely document-shaped chat state with the licence accepted | Postgres via operator | MongoDB is SSPL; corporate packs often deny it. When Postgres is denied, `apps/databases/mariadb` is the relational alternative. |
| `semantic` | `apps/databases/lancedb` | `apps/databases/lancedb` | `apps/databases/milvus` when the single-writer model is the bottleneck | Only when the use case retrieves from unstructured text. Milvus needs etcd and MinIO. |
| `artifacts` | `apps/minio/dev` | `apps/minio/single-server` | MinIO Tenant via the operator in base, or an S3-compatible service within residency | Buckets per kind: `inbox`, `parsed`, `audit`, `seed`. Object keys carry the idempotency key. |

## Default shapes

**Chat agent (support copilot)**: `session` → Redis; `working` and `episodic` → Postgres; no `semantic` (orders API is the lookup); `artifacts` → MinIO only if transcripts must be exported for audit. Crawl may keep session in Postgres and say so.

**Document intake (invoices)**: `artifacts` → MinIO (inbox, parsed, audit); `working` → Postgres (mailbox cursor, approval status); `episodic` → Postgres (extraction per invoice, decisions); no `session`; no `semantic` unless matching needs free-text retrieval across past invoices.

**Migration**: `working` → Postgres (progress, checkpoints; Redis acceptable for a checkpoint store if a restart from zero is cheap); `artifacts` → MinIO (verification report). Nothing else.

## Secrets the stores need

Catalog databases expect the overlay to supply a Secret with a fixed name (`postgres-secret`, `mongodb-secret`, `redis-secret`, `nats-secret`); the kustomize skill writes the `.env.example`. Your record names the stores; it does not carry credentials.

## Sizing hints for `risks`

Postgres single StatefulSet: fine to tens of GB and hundreds of writes per second; the operator at Run is for HA, not for size. Redis: memory-bound; name the eviction policy. LanceDB: single writer; concurrent ingestion is the limit. MinIO single server: no redundancy; the Run gate is the Tenant.

## `storageClassName` is an overlay parameter

Observed in a production tenant: one global patch targeting every PVC plus a `volumeClaimTemplates/0` patch per StatefulSet, because catalog components either omit the class (k3d default `local-path` at Crawl) or hard-code one. Your record names the class per stage (`local-path` at Crawl, `longhorn` from Walk, as the devops record's `storage_class`) in `rationale`; the kustomize skill writes:

```yaml
patches:
  - target: { kind: PersistentVolumeClaim }
    patch: |
      - op: add
        path: /spec/storageClassName
        value: longhorn
  - path: patches/postgres-storage-patch.yaml          # /spec/volumeClaimTemplates/0/spec/storageClassName
    target: { kind: StatefulSet, name: postgres }
```

## Init Jobs for multi-database Postgres and Mongo

When several workloads share one Postgres or Mongo (the tenant pattern: one StatefulSet, many databases), name it in `rationale` as the `multi-database init` pattern so the kustomize skill ships it: a `POSTGRES_MULTIPLE_DATABASES=app1,app2` env on the StatefulSet with an init script, or `init-mongo.js` through a `configMapGenerator` with `disableNameSuffixHash: true`, applied by an `<app>-init-job.yaml` with `ttlSecondsAfterFinished` and `backoffLimit`. Those Jobs assert nothing; the verify Job does. One database per workload, credentials per database in their own Secret, and the system-of-record rule still applies: none of them is a copy of the ERP.

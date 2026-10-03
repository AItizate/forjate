# Retention and backup per stage

## Retention defaults

| Kind | Crawl | Walk | Run |
|------|-------|------|-----|
| `session` | the ephemeral TTL (`4h`) | `24h` | `24h`, or the brief's conversation window |
| `working` | ephemeral TTL | until the unit completes, then `7d` | until completion plus `30d` |
| `episodic` | ephemeral TTL | `90d` or the business's answer | the legal retention for the data class, as an open question blocking Run unless the brief gives it |
| `semantic` | ephemeral TTL | while the corpus is current; re-index on change | same, with a versioned corpus |
| `artifacts` | ephemeral TTL | `90d` for inputs, evidence until the episodic retention | evidence retention from legal (financial documents are commonly years, not days) |

Regulated data: shortest retention that serves the KPI for operational copies, plus one audit copy with the legal retention, in a bucket with object locking at Run. The compliance expert reconciles your numbers with legal; your job is to make each number explicit per kind.

## Backup per stage

| Stage | `settings.backup` | What it means |
|-------|-------------------|---------------|
| Crawl | `none` | the environment is disposable; the seed Job recreates everything |
| Walk | `snapshot+dump` | Longhorn snapshots of the PVCs plus a nightly logical dump (`pg_dump`, `redis` RDB, MinIO mirror) to a MinIO bucket on a different node |
| Run | `velero+pitr` | Velero to an offsite target, Postgres operator with point-in-time recovery, MinIO Tenant with versioning |

## The restore gate

A backup that was never restored is a hope. Every Walk and Run record carries a `G-DS-<n>` gate "restore of <store> rehearsed from the last backup into a scratch namespace, row count verified", with `check.type: verify-job` or `ci` and the procedure named, and `restore_tested: false` in settings until it passes. The devops expert operates it; you demand it.

## Residency

`settings.data_residency` carries the region the brief or pack states. Every store in `choice` runs on cluster PVCs (Longhorn) inside that region at Walk and Run; a managed service appears only within the region and is named in `rationale`. A pack residency that contradicts the brief is an open question with `caused_by_rule`, never a silent choice of one or the other.

## Where the PVC lives

Residency is per store, and a store is a PVC on a StorageClass. `local-path` at Crawl (k3d, node-local, dies with the cluster), `longhorn` from Walk (three replicas across the nodes, snapshots for the backup ladder). The class is set by the overlay, not by the component: one global PVC patch plus per-StatefulSet patches (`components-per-stage.md`). A component whose PVC lands on the wrong class is the first thing a restore rehearsal finds.

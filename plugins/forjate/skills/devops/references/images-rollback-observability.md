# Images, rotation, backup, rollback, observability

## Image flow

| Stage | `image_registry` | `image_tag_policy` | `image_writeback` | `image_signing` |
|-------|------------------|--------------------|-------------------|-----------------|
| Crawl | the local k3d registry (`apps/docker-registry`) or GHCR with a `dev` tag | `any` | `none` (the runner applies the working tree) | `none` |
| Walk | GHCR or the org registry, pull secret on the ServiceAccount | `sha` (full commit SHA, never `latest`) | `repository_dispatch+yq` | `none` |
| Run | same | `semver+sha` for releases | same | `cosign` in CI (`docs/lab-to-production.md`; not in the catalog, name the CI step) |

The write-back, as a real tenant runs it (`docs/ci-cd.md`, `docs/ci-write-back-integration.md`, `tenant-patterns.md`):

1. The app repo's CI builds and pushes `ghcr.io/<org>/<app>:<sha>`.
2. Its last step fires `repository_dispatch` (`event_type: update-image-tag` or `app-image-updated`) at the IaC repo with `app_name`, `new_tag`, `env`.
3. The IaC workflow runs `yq -i '(.images[] | select(.name == "<image>")).newTag = "<sha>"' k8s/overlays/usecases/<name>/stages/<env>/kustomization.yaml`, commits `chore(deploy): update <app> to <sha> in <env>` under `concurrency: gitops-<env>-<app>`, and pushes to the branch or opens the PR the posture requires.
4. ArgoCD syncs.

Requirements the record states: the image is declared in an `images:` block (not a `sed`-able string in a patch); the workflow validates the build before committing; the dispatch token is a secret in the app repo; `env` selects a distinct stage overlay.

## Secret rotation

| Stage | `secret_rotation` | What exists |
|-------|-------------------|-------------|
| Crawl | `none` | the environment dies with its TTL |
| Walk | `scripted` | `scripts/rotate-secrets.sh <overlay>`: for every `secrets/*.env.example`, regenerate values per the header's `# To generate:` line, re-seal per `# To seal:`, commit the new `sealed-*.yaml`; `apps/monitoring/reloader` restarts consumers on Secret change; rehearsed once before Run (`G-OPS-<n>`, `manual`, `rotation-rehearsal`, operator named) |
| Run | `store-managed` | rotation in the external store; External Secrets `refreshInterval` picks it up; the same rehearsal gate |

Before the first real secret is sealed at Walk: the sealed-secrets controller key is backed up offsite (`kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml`, encrypted, outside the cluster). A cluster rebuild without it loses every secret in git. `G-OPS-<n>`, `manual`, ref `controller-key-backup`, operator named; verified by restoring the key into a scratch cluster.

## Backup and restore

`backup` is the data-store record's value; you operate it:

| `backup` | Operation | Rehearsal gate |
|----------|-----------|----------------|
| `none` (Crawl) | the seed Job recreates everything | n/a |
| `snapshot+dump` (Walk) | Longhorn recurring snapshots on the PVCs plus a nightly CronJob: `pg_dump` to a MinIO bucket on another node, Redis RDB, `mc mirror` for buckets | restore into a scratch namespace, row counts compared (`restore-rehearsal`, `manual`, operator named); `restore_rehearsed: false` until done |
| `velero+pitr` (Run) | Velero to an offsite target within residency, Postgres operator with WAL archiving for point-in-time recovery, MinIO Tenant versioning | the same rehearsal, from the offsite target |

Velero is not a catalog component (issue #6 in `docs/lab-to-production.md`). The record keeps the target the data-store set, names the gap and raises the open question (offsite target within residency, who operates it); it never lists `apps/backup/velero` in `choice`.

## Rollback runbook

`rollback: redeploy-ephemeral` at Crawl (`ephemeral.sh down && up`). From Walk, `git-revert+argocd-sync`, steps in `rationale`:

1. `argocd app history uc-<name>-<stage>` to find the last good revision.
2. `git revert <bad sha>` (or bump the tag back), push to what the Application tracks.
3. `argocd app sync uc-<name>-<stage>` and watch the canary verify Job and the KPI metric.
4. If data changed shape, this is the restore gate, not a rollback; say so.

`rollback_rehearsed: false` until done once on Walk (`G-OPS-<n>`, `manual`, `rollback-rehearsal`, operator named). Image-only rollback is a write-back with the previous SHA.

## Observability baseline

| Stage | `observability` | `choice` | `alerting` |
|-------|-----------------|----------|------------|
| Crawl | `none` | nothing; the runner prints Job logs | `none` |
| Walk | `prometheus+grafana` | `apps/monitoring/prometheus`, `apps/monitoring/grafana` | `alertmanager` with the three alerts that page |
| Run | `prometheus+grafana+otel` | plus `apps/monitoring/otel-collector` for traces of model and tool calls | plus SLO burn-rate alerts |

`golden_signals` per workload: latency p95, error rate, saturation (queue depth, memory), traffic; plus the quality record's signals (KPI, escalation rate, tool failure rate, tokens and cost per item, eval pass rate). The three alerts that page at Walk: the canary verify Job failing, error rate above the SLA, cost per item above the AI-engineering budget. Everything else is a dashboard. A `metric` gate in the quality record needs a stack here; a pack that denies the stack is an open question about where the metric lives, raised in both records.

## Conventions a real tenant uses (for the kustomize skill, named in your record when relevant)

- `replicas: 0` with a comment `# Temporarily scaled to 0 — hardware constraints` is how a tenant parks a workload; the record's `risks` lists parked workloads.
- `imagePullSecrets` on every ServiceAccount through one patch targeting `kind: ServiceAccount` without a name.
- A global PVC `storageClassName` patch plus per-StatefulSet `volumeClaimTemplates/0` patches when a component hard-codes a class.
- Init Jobs with `ttlSecondsAfterFinished` and `backoffLimit`, not suspended, for multi-database setup; they assert nothing, which is why the verify Job exists.

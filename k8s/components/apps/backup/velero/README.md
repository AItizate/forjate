# Velero — cluster-level backup and restore

Backs up Kubernetes objects and PVC data (CSI snapshots, or file-system backup through the node agent) to an S3-compatible bucket, on a schedule, and restores them whole or by namespace. It also moves a namespace between clusters.

It **adds to** app-level logical dumps (`pg_dump` to MinIO CronJobs), it does not replace them. Keep both: Velero rebuilds the cluster state, the dump proves the data restores into a fresh database.

## What is in the component

| File | Purpose |
|------|---------|
| `kustomization.yaml` | Namespace plus the `velero` Helm chart, pinned (chart 12.2.2, Velero 1.18.2, AWS plugin 1.13.1) |
| `values-minio-backend.yaml` | **Default.** Backs up to the in-cluster MinIO (`apps/minio/single-server`), bucket `velero` |
| `s3/` | **Opt-in variant.** Same chart, external S3-compatible store (AWS S3, Cloudflare R2, B2), file-system backup without CSI, CRDs as plain resources. Reference this directory instead of the parent; tenants patch only data |
| `examples/schedule-daily.yaml` | Daily full backup at 02:00, kept 30 days (CSI snapshots) |
| `examples/schedule-weekly-fs.yaml` | Weekly full backup, Sunday 03:00, kept 4 weeks, file-system backup |
| `examples/backuplocation-minio.yaml` | The MinIO target as a standalone object, for a second location |

Render: `kubectl kustomize --enable-helm k8s/components/apps/backup/velero` (or `.../velero/s3`)

## Before you deploy

1. Deploy `apps/minio/single-server` (default backend) and create a bucket named `velero`.
2. Create the credentials Secret in the `velero` namespace. The file uses the AWS credentials format and never goes in git unsealed:

   ```bash
   kubectl -n velero create secret generic velero-credentials \
     --from-file=cloud=<(printf '[default]\naws_access_key_id=%s\naws_secret_access_key=%s\n' "$KEY" "$SECRET")
   ```

3. Confirm the cluster has a CSI driver with a `VolumeSnapshotClass` (Longhorn does) labelled `velero.io/csi-volumesnapshot-class: "true"`. Without one, set `defaultVolumesToFsBackup: true` on the schedule to use the node agent instead.

The namespace is labelled `privileged` because the node agent mounts host paths. Everything else about the component runs fine under tighter admission.

## Switching backend

An in-cluster MinIO does not survive the loss of the cluster, so it is a first step, not DR. To back up off-cluster, reference `backup/velero/s3` instead of `backup/velero` (next section). Keep the same Secret name and key. Alternatively keep MinIO and replicate the `velero` bucket off-site.

## External S3 or R2 from a remote tenant

`s3/` is a complete variant of the component, so a tenant consumes it by path and never copies the `helmCharts` entry. Both the parent and `s3/` create the namespace `velero` and a Helm release named `velero`: reference one of them, not both.

What `s3/` does differently from the default:

- **Backend.** One `BackupStorageLocation` named `default`, with R2-ready defaults: `region: auto`, `s3ForcePathStyle: "true"`, `checksumAlgorithm: ""` (velero-plugin-for-aws 1.10 and later send a checksum R2 rejects). The bucket and endpoint are `CHANGE-ME` placeholders the tenant patches.
- **Volume data without CSI.** No `VolumeSnapshotLocation`, no `EnableCSI`; the node agent backs up PVC contents with kopia and the server defaults to `--default-volumes-to-fs-backup`. A k3s cluster with Longhorn or local-path and no snapshot-controller works as is.
- **CRDs as plain resources.** `includeCRDs: true` with `upgradeCRDs: false`, so there is no pre-install hook Job running `kubectl`. Argo CD applies the CRDs before the custom resources in the same sync.

A remote tenant's `kustomization.yaml`:

```yaml
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/backup/velero/s3?ref=v1.2.0
  - velero-credentials.sealed.yaml   # Secret velero-credentials, key cloud
  - schedule-weekly.yaml             # copy of examples/schedule-weekly-fs.yaml

patches:
  - target:
      group: velero.io
      kind: BackupStorageLocation
      name: default
    patch: |-
      apiVersion: velero.io/v1
      kind: BackupStorageLocation
      metadata:
        name: default
        namespace: velero
      spec:
        objectStorage:
          bucket: my-cluster-backups
          prefix: velero
        config:
          s3Url: https://<account-id>.r2.cloudflarestorage.com
```

For AWS S3 itself, patch `config.region` to the bucket's region and remove `s3Url`, `s3ForcePathStyle` and `checksumAlgorithm` (a JSON 6902 `remove` op each). For B2, MinIO elsewhere or another S3-compatible store, patch `s3Url` and `region`; `checksumAlgorithm: ""` is harmless there.

The R2 credentials are an R2 API token with Object Read & Write on the bucket, written in the AWS credentials format shown in "Before you deploy". Seal it (`sealed-secrets`) or deliver it with your secret manager; never commit it in clear.

**Argo CD.** The component uses the Kustomize `helmCharts` generator, which Argo CD only runs with Helm enabled. Set it once in `argocd-cm` (the factory's `continuous-delivery/argocd` does not set it for you):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-cm
  namespace: argocd
data:
  kustomize.buildOptions: --enable-helm
```

Without it the sync fails with `must specify --enable-helm`.

**Turning CSI snapshots on.** Only when the cluster has the snapshot-controller and a `VolumeSnapshotClass` labelled `velero.io/csi-volumesnapshot-class: "true"`. Add the feature flag to the server and switch the schedule:

```yaml
patches:
  - target: {kind: Deployment, name: velero}
    patch: |-
      - op: add
        path: /spec/template/spec/containers/0/args/-
        value: --features=EnableCSI
```

and in the Schedule `snapshotVolumes: true`, `defaultVolumesToFsBackup: false`.

### Weekly schedule, 4 weeks of retention

`examples/schedule-weekly-fs.yaml` runs every Sunday at 03:00 and keeps each backup for `672h` (28 days), so four weekly backups exist at any time:

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: weekly-full
  namespace: velero
spec:
  schedule: "0 3 * * 0"
  template:
    ttl: 672h
    includedNamespaces: ["*"]
    excludedNamespaces: [velero, kube-system]
    includeClusterResources: true
    snapshotVolumes: false
    defaultVolumesToFsBackup: true
    storageLocation: default
```

### Excluding volumes

With file-system backup on by default, every pod volume is copied. Leave out caches, scratch space and volumes whose data comes back from elsewhere with an annotation on the **pod template**:

```yaml
metadata:
  annotations:
    backup.velero.io/backup-volumes-excludes: cache,tmp   # volume names in the pod spec
```

Exclude a whole namespace with `excludedNamespaces` on the Schedule, or any object with the label `velero.io/exclude-from-backup: "true"`.

`hostPath` volumes are never backed up by the node agent. The k3s local-path provisioner creates `hostPath` PVs by default; set `volumeType: local` on its StorageClass (or the PVC annotation `volumeType: local`) for volumes that must be in the backup, and check `velero backup describe <name> --details` lists them.

### Consistent database backups: pre-backup hooks

A file copy of a running database's data directory can be torn. Have Velero dump first, into a volume that is backed up, through annotations on the database pod template:

```yaml
# PostgreSQL
metadata:
  annotations:
    pre.hook.backup.velero.io/container: postgres
    pre.hook.backup.velero.io/command: '["/bin/sh", "-c", "pg_dumpall -U postgres > /var/lib/postgresql/data/velero-dump.sql"]'
    pre.hook.backup.velero.io/timeout: 10m
    pre.hook.backup.velero.io/on-error: Fail
```

```yaml
# MongoDB
metadata:
  annotations:
    pre.hook.backup.velero.io/container: mongodb
    pre.hook.backup.velero.io/command: '["/bin/sh", "-c", "mongodump --archive=/data/db/velero-dump.archive --gzip"]'
    pre.hook.backup.velero.io/timeout: 10m
    pre.hook.backup.velero.io/on-error: Fail
```

The dump lands in the data volume, so the file-system backup carries a consistent copy next to the live files; restore from the dump if the live files do not start cleanly. Add credentials through the container's existing environment (`PGPASSWORD`, `--uri`), never inline. A `post.hook.backup.velero.io/command` can delete the dump afterwards. These hooks complement, not replace, the app-level dump CronJobs.

## Schedule a backup

```bash
kubectl apply -f k8s/components/apps/backup/velero/examples/schedule-daily.yaml
velero backup create first-run --from-schedule daily-full   # run one now
velero backup get                                           # wait for Phase: Completed
```

## Restore runbook

Rehearse this before you need it. A backup nobody has restored is a guess.

**Example: the namespace `agentic-simple-workflow` was deleted by mistake.**

1. Confirm the backup exists and finished:

   ```bash
   velero backup get
   velero backup describe daily-full-<timestamp> --details   # Phase: Completed, no errors
   ```

2. Make sure the namespace is gone or empty. Velero skips objects that already exist; it does not overwrite them.

   ```bash
   kubectl get ns agentic-simple-workflow
   ```

3. Restore only that namespace:

   ```bash
   velero restore create --from-backup daily-full-<timestamp> \
     --include-namespaces agentic-simple-workflow
   ```

4. Watch it and read the result:

   ```bash
   velero restore get
   velero restore describe <restore-name> --details
   velero restore logs <restore-name>
   ```

5. Verify the workload, not just the restore status:

   ```bash
   kubectl -n agentic-simple-workflow get pods,pvc
   kubectl -n agentic-simple-workflow rollout status deploy --timeout=5m
   ```

   Then check the data itself (a row count, a file, a login) against what you expect.

**Whole-cluster loss.** Build a fresh cluster, deploy this component with the same bucket and credentials, wait for the location to show `Available` (`velero backup-location get`), then `velero backup get` lists the old backups. Restore in this order: cluster-scoped resources and operators first (CRDs, MinIO operator, Longhorn), then the data namespaces, then the rest.

**Restoring to another cluster or namespace.** Add `--namespace-mappings old:new`. Storage classes must exist in the target.

**Known limits.** Longhorn volumes restored from a CSI snapshot need the same Longhorn version family. Secrets restored from a backup include the sealed-secrets controller key only if `sealed-secrets` is in the backed-up namespaces; back that key up separately as well. Restores do not re-run `pg_dump` CronJobs; use them for point-in-time data checks.

## Where it fits

It is the gate between MVP and Production in [`docs/lab-to-production.md`](../../../../../docs/lab-to-production.md). Add it to any overlay that holds real state.

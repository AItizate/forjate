# Velero — cluster-level backup and restore

Backs up Kubernetes objects and PVC data (CSI snapshots, or file-system backup through the node agent) to an S3-compatible bucket, on a schedule, and restores them whole or by namespace. It also moves a namespace between clusters.

It **adds to** app-level logical dumps (`pg_dump` to MinIO CronJobs), it does not replace them. Keep both: Velero rebuilds the cluster state, the dump proves the data restores into a fresh database.

## What is in the component

| File | Purpose |
|------|---------|
| `kustomization.yaml` | Namespace plus the `velero` Helm chart, pinned (chart 12.2.2, Velero 1.18.2, AWS plugin 1.13.1) |
| `values-minio-backend.yaml` | **Default.** Backs up to the in-cluster MinIO (`apps/minio/single-server`), bucket `velero` |
| `values-s3-backend.yaml` | **Opt-in.** Backs up to an external S3 store; replace the `CHANGE-ME` values |
| `examples/schedule-daily.yaml` | Daily full backup at 02:00, kept 30 days |
| `examples/backuplocation-minio.yaml` | The MinIO target as a standalone object, for a second location |

Render: `kubectl kustomize --enable-helm k8s/components/apps/backup/velero`

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

An in-cluster MinIO does not survive the loss of the cluster, so it is a first step, not DR. To back up off-cluster, copy the component into your overlay and point `valuesFile` at `values-s3-backend.yaml`:

```yaml
helmCharts:
  - name: velero
    repo: https://vmware-tanzu.github.io/helm-charts
    version: 12.2.2
    releaseName: velero
    namespace: velero
    valuesFile: values-s3-backend.yaml
```

Keep the same Secret name and key. Alternatively keep MinIO and replicate the `velero` bucket off-site.

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

## Recommended in

`agentic-simple-workflow`, `home-edge-lab` and `multi-cloud-portable` hold real state and list this component as recommended. It is the gate between MVP and Production in [`docs/lab-to-production.md`](../../../../../docs/lab-to-production.md).

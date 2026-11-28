# SeaweedFS

S3-compatible object storage (Apache-2.0), run by the
[seaweedfs-operator](https://github.com/seaweedfs/seaweedfs-operator). The component ships the
operator with its CRDs and one `Seaweed` cluster named `seaweedfs`. It sets no namespace; the
overlay places it:

| Pod | request | limit | PVC |
|---|---|---|---|
| operator | 64Mi | 256Mi | – |
| master | 128Mi | 512Mi | 1Gi |
| volume | 256Mi | 1Gi | 10Gi |
| filer (leveldb2 metadata) | 256Mi | 1Gi | 1Gi |
| S3 gateway (IAM embedded) | 128Mi | 512Mi | – |

Replication is `000`: one copy, durability from the StorageClass. All pods meet Pod Security
`restricted`. WebDAV, SFTP, the admin UI and Ingress are off. S3 is plain HTTP inside the
cluster at `http://seaweedfs-s3.<namespace>.svc:8333`, path-style.

The operator's admission webhook is off: its chart bakes the release namespace into the
webhook certificate, and the webhook only validates the `Seaweed` spec. A bad tenant patch
surfaces in the operator's reconcile, not at admission.

Pinned 2026-11-24: chart `seaweedfs-operator` 0.1.49, operator 1.0.46, SeaweedFS 4.55.

## Prerequisites

- `kustomize build --enable-helm`. Argo CD needs `kustomize.buildOptions: --enable-helm` in
  `argocd-cm`.
- A StorageClass. Unset means the cluster default.
- One instance per cluster: the operator watches all namespaces and owns cluster-scoped CRDs
  and ClusterRoles.

## Consume it

```yaml
namespace: storage            # any name; the overlay also ships the Namespace
resources:
  - namespace.yaml             # e.g. pod-security.kubernetes.io/enforce: restricted
  - ../../components/apps/storage/seaweedfs
```

Then, per consumer namespace:

1. Label the namespace `forjate.io/object-store-client: "true"`. The NetworkPolicy admits port
   8333 only from labelled namespaces; master, volume and filer ports stay closed to everyone
   outside the component's namespace.
2. Declare the operator's CRs in the overlay
   ([upstream samples](https://github.com/seaweedfs/seaweedfs-operator/tree/1.0.46/config/samples)):
   - a `ResourceReferenceGrant` in the component's namespace, once per cluster, so CRs in
     other namespaces can reference the `Seaweed`. Without it they stay `Pending`;
   - a `Bucket`;
   - an `S3Identity` and its `S3Credentials`. The operator generates the key pair and writes it
     to a Secret in the consumer's namespace. Set `accessKeyField: AWS_ACCESS_KEY_ID` and
     `secretKeyField: AWS_SECRET_ACCESS_KEY` so SDKs read it through `envFrom`;
   - an `S3Policy` scoped to the bucket and its `S3PolicyBinding`. Other buckets are denied.

   Annotate them with `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true`, so the
   first sync does not fail before the CRDs exist. A use case with this wiring is #78.

## What to patch

On the `Seaweed` `seaweedfs`:

- `spec.master.persistence.storageClassName`, `spec.filer.persistence.storageClassName`,
  `spec.volume.storageClassName`;
- sizes: `spec.master.persistence.resources.requests.storage`,
  `spec.filer.persistence.resources.requests.storage`, `spec.volume.requests.storage`
  (measured data × 2 for vacuum and growth);
- `requests`/`limits` per pod. On k3d, after a 200 MiB upload and 300 small objects, the peak
  was: master 32Mi, operator 37Mi, filer 89Mi, volume 321Mi (about 100Mi of it process
  memory, the rest page cache), S3 gateway 337Mi. The gateway grows with concurrent
  multipart uploads;
- Run: HA is a change to the CR (more `replicas` per server, `defaultReplication`), not a
  different component. That shape is not exercised in this factory yet.

## Upgrade

Bump the chart `version` and `image.tag` in `kustomization.yaml` and `spec.image` in
`seaweed.yaml` together, from the operator's release notes. A tenant can override
`spec.image` in its overlay to pick up a SeaweedFS security fix before the factory bumps.
The filer's leveldb2 store holds every object's metadata: snapshot it (the operator's
`SeaweedBackup`) before an upgrade that touches the filer.

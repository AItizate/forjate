# SeaweedFS

S3-compatible object storage (Apache-2.0), run by the
[seaweedfs-operator](https://github.com/seaweedfs/seaweedfs-operator). The component ships the
operator with its CRDs and one `Seaweed` cluster named `seaweedfs` in namespace `seaweedfs`:

| Pod | request | limit | PVC |
|---|---|---|---|
| operator | 64Mi | 256Mi | – |
| master | 128Mi | 512Mi | 1Gi |
| volume | 256Mi | 1Gi | 10Gi |
| filer (leveldb2 metadata) | 256Mi | 1Gi | 1Gi |
| S3 gateway (IAM embedded) | 128Mi | 512Mi | – |

Replication is `000`: one copy, durability from the StorageClass. All pods run under Pod
Security `restricted`. WebDAV, SFTP, the admin UI and Ingress are off. S3 is plain HTTP inside
the cluster at `http://seaweedfs-s3.seaweedfs.svc:8333`, path-style.

Pinned 2026-11-24: chart `seaweedfs-operator` 0.1.49, operator 1.0.46, SeaweedFS 4.55.

## Prerequisites

- `kustomize build --enable-helm`. Argo CD needs `kustomize.buildOptions: --enable-helm` in
  `argocd-cm`.
- A StorageClass. Unset means the cluster default.

## Consume it

```yaml
resources:
  - ../../components/apps/storage/seaweedfs
```

Then, per consumer namespace:

1. Label the namespace `forjate.io/object-store-client: "true"`. The NetworkPolicy admits port
   8333 only from labelled namespaces; master, volume and filer ports stay closed to everyone
   outside `seaweedfs`.
2. Copy what you need from `examples/` (not part of `resources`):
   - `reference-grant.yaml`: once per cluster; lets labelled namespaces reference the `Seaweed`.
     Apply it with or before the CRs below, or they stay `Pending` until it exists.
   - `bucket.yaml`: a `Bucket`.
   - `identity.yaml`: an `S3Identity` and its `S3Credentials`. The operator generates the key
     pair and writes it to a Secret in the consumer's namespace as `AWS_ACCESS_KEY_ID` /
     `AWS_SECRET_ACCESS_KEY`. Nothing secret is committed.
   - `policy.yaml`: an `S3Policy` scoped to one bucket and its `S3PolicyBinding`. Other buckets
     are denied.
   - `client-config.yaml`: the ConfigMap with `AWS_ENDPOINT_URL`, `AWS_REGION` and the bucket.
     Mount it together with the Secret through `envFrom`.

The examples carry `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true`, so the
first sync does not fail before the CRDs exist.

## What to patch

On the `Seaweed` `seaweedfs`:

- `spec.master.persistence.storageClassName`, `spec.filer.persistence.storageClassName`,
  `spec.volume.storageClassName`;
- sizes: `spec.master.persistence.resources.requests.storage`,
  `spec.filer.persistence.resources.requests.storage`, `spec.volume.requests.storage`
  (measured data × 2 for vacuum and growth);
- `requests`/`limits` per pod. On k3d, after a 200 MiB upload and 300 small objects, the peak
  was: master 36Mi, filer 79Mi, operator 35Mi, S3 gateway 309Mi, volume 330Mi (about 100Mi of
  it process memory, the rest page cache). The gateway grows with concurrent multipart uploads.

## Upgrade

Bump the chart `version` and `image.tag` in `kustomization.yaml` and `spec.image` in
`seaweed.yaml` together, from the operator's release notes. A tenant can override
`spec.image` in its overlay to pick up a SeaweedFS security fix before the factory bumps.
The filer's leveldb2 store holds every object's metadata: snapshot it (the operator's
`SeaweedBackup`) before an upgrade that touches the filer.

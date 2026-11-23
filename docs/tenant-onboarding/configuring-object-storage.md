# Configuring Object Storage (the S3 contract)

Components that keep objects (backups, mail blobs, documents, vectors' segments) reach an S3 endpoint through
one **contract**: a Secret and a config with fixed key names, supplied by the tenant. No consumer names the store
behind it, so a tenant can run an in-cluster store, an external S3 service or a Ceph gateway without touching the
consumer. Persistent volumes for the stores themselves are a separate topic: see
[Configuring Persistent Storage](configuring-storage.md).

The plan that introduces the contract, and the replacement of MinIO, is tracked in
[#72](https://github.com/AItizate/forjate/issues/72).

## The contract

The key names are the **AWS SDK standard names**, so an SDK-based client reads them with no glue.

**Secret, one per consumer identity.** The tenant creates it and chooses its name; the consumer's catalog entry
declares which name it expects (`wiring.consumes`, below).

| Key | Meaning |
|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the identity's keys, scoped to its own buckets |

**Config, per binding** (a ConfigMap, or the same Secret; none of it is secret):

| Key | Meaning |
|---|---|
| `AWS_ENDPOINT_URL_S3` | full URL, e.g. `http://<service>.<namespace>.svc:8333` |
| `S3_HOST`, `S3_PORT`, `S3_USE_TLS` | the same endpoint split, for clients that need `host:port` and a flag; they must agree with the URL |
| `AWS_REGION` | the region; any value for an in-cluster store, `auto` for Cloudflare R2 |
| `S3_BUCKET`, or `S3_BUCKET_<ROLE>` | the bucket, or one key per bucket for a consumer with several (`S3_BUCKET_MEDIA`, `S3_BUCKET_EXPORTS`) |
| `AWS_CA_BUNDLE` + `ca.crt` (optional) | only when the endpoint uses a private CA |

Rules:

- A consumer with several buckets uses **one identity Secret and several bucket keys**, never several `envFrom`
  Secrets whose `AWS_*` names collide.
- **Path-style addressing** is the default. There is no standard SDK variable for it, so each consumer sets its
  own flag (see the mapping).
- In-cluster endpoints are **plain HTTP by default**, restricted by a NetworkPolicy; TLS with a private CA is
  opt-in, and then `AWS_CA_BUNDLE` points at the mounted `ca.crt`.
- One identity per application. No shared root keys; a store's administrator credentials never reach a consumer.

Example, for a consumer that reads the contract with `envFrom`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-app-s3
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: <access-key>       # seal it; see docs/tenant-onboarding/agent-secrets.md
  AWS_SECRET_ACCESS_KEY: <secret-key>
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-app-s3
data:
  AWS_ENDPOINT_URL_S3: http://s3.object-store.svc:8333
  S3_HOST: s3.object-store.svc
  S3_PORT: "8333"
  S3_USE_TLS: "false"
  AWS_REGION: us-east-1
  S3_BUCKET: my-app
```

## Per-consumer mapping

Applications that do not read the AWS names take them through `secretKeyRef` / `configMapKeyRef` under their own
variable names. The application's variable names (`MINIO_ADDRESS`, `APPFLOWY_S3_USE_MINIO`) stay; what changes is
that their **values** come from the contract instead of a hard-wired host or a default credential.

| Consumer | How it reads the contract |
|---|---|
| `databases/milvus` | `MINIO_ADDRESS` = `S3_HOST:S3_PORT`, `MINIO_USE_SSL` = `S3_USE_TLS`, `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` by `secretKeyRef` to the identity, bucket = `S3_BUCKET`. A single local lab can instead run Milvus standalone with local storage and no S3 |
| `productivity/appflowy` | three Deployments (`appflowy-cloud`, `worker`, `ai`): `APPFLOWY_S3_USE_MINIO=true` and `AI_USE_MINIO=true` are upstream's switches for any custom endpoint; the URL from `AWS_ENDPOINT_URL_S3`, the keys by `secretKeyRef` |
| `communication/stalwart` | the keys are already `%{env:…}%`; the endpoint becomes `%{env:AWS_ENDPOINT_URL_S3}%` where Stalwart expands it, otherwise the tenant patches the literal |
| `backup/velero` | Velero's own `cloud` ini Secret (`[default]` with `aws_access_key_id` / `aws_secret_access_key`) built from the identity, and the `BackupStorageLocation` `s3Url`, `bucket`, `region` patched by the tenant; `caCert` when TLS |

Each row is verified, and the consumer rewired, in its own change; until then the catalog lists the file in the
coupling baseline (below).

## How the catalog carries it

- The capability `object-store` in `wiki/catalog-capabilities.yaml` holds the contract: its `protocol` (`s3`), the
  `secret_keys`, the `config_keys` and the `config_key_patterns` (`S3_BUCKET_<ROLE>`).
- A **provider** lists `object-store` (and `artifact-store`, the need the use-case builder asks for) in
  `wiki/catalog-overrides.yaml`.
- A **consumer** declares what it reads in its override:

  ```yaml
  wiring:
    consumes:
      - protocol: s3
        secret: my-app-s3          # the Secret the overlay supplies
        keys: [AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL_S3, S3_BUCKET]
        format: env                # env | velero-cloud | config-file
  ```

  `scripts/wiki-compile.py` checks its shape and copies it into `wiki/catalog.json`.

## Checks

Three repo-wide checks run as steps of `.github/workflows/validate-kustomize.yml`. They read the catalog and name
no component or vendor.

| Check | Fails when |
|---|---|
| `scripts/checks/object-store-coupling-check.sh` | a component that does not provide `object-store` carries, as a value, a provider's Service, pod label, Secret name or image repository, or a pod's S3 credential variable has a literal value |
| `scripts/checks/object-store-contract-check.sh` | a `wiring.consumes` declaration uses a protocol no capability's contract defines, or a key outside that contract |
| `scripts/checks/pin-check.sh` | a source under `k8s/base` or `k8s/components` pulls a remote resource off a tag or commit, a `helmCharts` entry has no exact `version`, or an image is untagged or `latest` |

The coupling and pin checks **ratchet** against a committed baseline (`*.baseline` next to them): a new offender
fails, and so does a baseline entry that no longer offends, so the baseline only shrinks. Fixing an offender means
removing its line in the same change.

## Implementations

The contract is a convention, not a component: any of these satisfies it, and the tenant can move between them by
copying the objects and rewriting the Secret and ConfigMap.

### In-cluster: SeaweedFS (default, planned)

A SeaweedFS component (operator and a single-shape store, pinned) is the planned default in-cluster implementation,
tracked in [#72](https://github.com/AItizate/forjate/issues/72). Buckets, identities and bucket-scoped policies are
declared as custom resources in git; each identity yields one contract Secret. Until it lands, the in-cluster
providers are the MinIO components, which are being retired.

### External S3 (Cloudflare R2, Backblaze B2, AWS S3)

The store lives outside the cluster; the cluster only holds the contract Secret and ConfigMap. Manage the buckets
and the bucket-scoped tokens with OpenTofu (or the provider's console for a lab) and seal the resulting keys.

| Service | `AWS_ENDPOINT_URL_S3` | `AWS_REGION` |
|---|---|---|
| Cloudflare R2 | `https://<account-id>.r2.cloudflarestorage.com` | `auto` |
| Backblaze B2 | `https://s3.<region>.backblazeb2.com` | the bucket's region |
| AWS S3 | omit it (the SDK default) or `https://s3.<region>.amazonaws.com` | the bucket's region |

`backup/velero/s3` already works this way; see its README.

### Rook-Ceph RGW (dedicated disks and nodes)

For a tenant with dedicated storage nodes, Rook's Ceph object gateway is the path; there is no component for it in
this factory. An `ObjectBucketClaim` yields a ConfigMap (`BUCKET_HOST`, `BUCKET_PORT`, `BUCKET_NAME`) and a Secret
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`); the tenant maps them to the contract keys, by a small Job or by
writing the contract ConfigMap from the claim's values.

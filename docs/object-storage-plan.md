# Object storage — MinIO replacement plan

Status: **proposed** · 2026-11-23 · Issue: [#72](https://github.com/AItizate/forjate/issues/72) ·
Evaluation: [`object-storage-evaluation.md`](object-storage-evaluation.md)

## Scope

Replace MinIO in this factory with:

1. an **S3 object-store contract** that every consumer component reads, so no component names the store;
2. a **SeaweedFS component** (operator + store, pinned) as the default in-cluster implementation;
3. an **external S3 profile** (R2, B2, AWS) as a first-class alternative, generalising `backup/velero/s3`;
4. **Rook-Ceph RGW** documented as the path for tenants with dedicated disks and nodes (not built here);
5. removal of MinIO from `k8s/base`, then from `components/`.

Then migrate the first remote tenant (Scitrix), then the others.

Out of scope in this repo: tenant-specific migration steps (they live in each tenant's runbook, per the
component-independence rule in `CLAUDE.md`), the interim hardening of running MinIO instances, and COSI adoption
(tracked, not adopted until it ships v1beta1; see the evaluation).

## Why

MinIO's community edition is archived and unpatched (CVEs from 2026-03/04 fixed only in the commercial AIStor),
the base pulls its archived operator without `?ref=`, two components run floating or frozen images, and four
components hard-wire a `minio` host. Details and dated sources: the evaluation, section 2.

## Principles

- **Test first.** Every stage starts by adding the check that fails today, and ends when it passes in CI.
- **One PR per stage**, each releasable on its own; no stage leaves `main` broken for remote tenants pinned to a tag.
- **Independence.** The contract is a convention (Secret shape + catalog wiring), not a component. No consumer
  component references SeaweedFS; the SeaweedFS component knows nothing about its consumers.
- **Pinned.** Chart version, operator image and SeaweedFS image are exact tags (plus digest where the gates
  require it); `image-policy-check.sh` and `ref-pinning-check.sh` already enforce this.

## Stage 0 — Red tests (one PR)

Add the checks the later stages turn green. They land marked as expected failures (or in report-only mode) so
CI stays green until the stage that fixes each one.

| Check | Where | Fails today because |
|---|---|---|
| `object-store-coupling-check.sh`: no file under `k8s/components/**` outside the store implementations names `minio` (host, env var, image, Secret) | `scripts/gates/checks/` | velero default values, stalwart, appflowy, milvus |
| Contract check: every component whose catalog wiring declares `protocol: s3` as a *consumer* reads the contract Secret keys, verified against the rendered pods | `scripts/gates/checks/`, catalog-driven (no component names in the script) | consumers read ad-hoc keys |
| `base` check: `kustomize build k8s/base` renders no `minio.min.io` kind and no `github.com/minio/*` resource | `validate-kustomize` | base pulls the operator |
| Ephemeral use case `object-storage` (contract `usecase.yaml`, seed + verify Jobs) | `k8s/overlays/usecases/object-storage/` | the SeaweedFS component does not exist |

The `object-storage` verify Job proves, against the real component on k3d:

1. a `Bucket` declared as a CRD exists and is reachable through the contract Secret;
2. an identity scoped to bucket A can write A and is **denied** on bucket B;
3. an agent pod gets short-lived credentials through STS `AssumeRoleWithWebIdentity` with its
   ServiceAccount token, and they expire;
4. presigned GET and PUT URLs work;
5. an anonymous-read bucket serves an object without credentials (the static-site pattern);
6. multipart upload of an object larger than the part size;
7. SSE is applied to stored objects (header round-trip);
8. Velero (`backup/velero/s3` pointed at the store through the contract) backs up and restores a namespace with a
   PVC (kopia file-system backup).

## Stage 1 — The contract (one PR)

Define it once, in `docs/tenant-onboarding/configuring-storage.md` (rewritten) and in the catalog:

- **Secret shape**, one Secret per consumer and bucket, AWS SDK standard keys so most clients need no glue:
  `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, plus `S3_BUCKET` and
  `S3_FORCE_PATH_STYLE`. Velero keeps its own `cloud` key format; the contract documents the mapping.
  *(Open question for review: AWS standard names vs a forjate prefix.)*
- **Bucket declaration** belongs to the tenant overlay, in the vocabulary of the chosen implementation
  (SeaweedFS `Bucket`/`S3Identity`/`S3Policy` CRDs, OpenTofu for R2, `ObjectBucketClaim` for Rook).
- **Catalog**: a new `object-store` capability provided by store implementations; `artifact-store` is satisfied
  by "any `object-store` provider + a bucket", not by a named component. Consumers declare
  `wiring.consumes: {protocol: s3, secret: <name>}`.
- Generic upgrade note: endpoint and Secret names are now tenant-supplied.

Tests turning green: contract check (schema only).

## Stage 2 — Rewire consumers (one PR per component, or one PR with one commit each)

| Component | Change |
|---|---|
| `backup/velero` | the default values no longer target an in-cluster MinIO; one values file, endpoint and bucket patched by the tenant (as `s3/` does); `values-minio-backend.yaml` removed |
| `communication/stalwart` | S3 blob store endpoint, bucket and keys from the contract Secret |
| `productivity/appflowy` | same |
| `databases/milvus` | `MINIO_*` env from the contract Secret (Milvus' own variable names, values from the contract); no default credentials in the manifest |
| builder plugin | `data-store` expert, references, evals and fixtures speak of `object-store`/`artifact-store`, not MinIO; golden records regenerated |
| docs | `docs/apps/minio.md` marked deprecated; prose in architecture/overlay docs updated |

Tests turning green: coupling check, contract check (rendered pods).

## Stage 3 — SeaweedFS component (one PR)

`k8s/components/apps/storage/seaweedfs/`:

- operator through the Kustomize `helmCharts` generator (like `backup/velero`), chart and images pinned to the
  latest release at build time (on 2026-11-23: chart `seaweedfs-operator-0.1.49`, operator `1.0.46`, SeaweedFS
  `4.55`), with a comment giving date and reason;
- a `Seaweed` CR with two documented profiles as sub-directories:
  `single/` (one master, one volume server, one filer + S3 gateway; homelab, Pi arm64, k3d) and
  `small/` (three volume servers for a three-node cluster);
- S3 gateway with IAM on, TLS through a cert-manager `Certificate` (placeholder issuer patched by the tenant),
  SSE on by default; SSE-KMS through OpenBao documented as an example, not wired (independence rule);
- `examples/`: `Bucket`, `S3Identity`, `S3Policy`, `S3PolicyBinding`, `S3Role` + `S3OIDCProvider` for agents
  (Kubernetes API server as OIDC issuer), anonymous-read bucket;
- PSA `restricted`, NetworkPolicy, resource requests sized for the small profile;
- catalog override (`capabilities: [object-store, artifact-store]`, licence Apache-2.0, maturity `mvp`, notes on
  the Enterprise-only features left out) and wiki recompile.

Open questions for review:

- Replication on Longhorn: SeaweedFS replication `000` on 2-replica Longhorn (≈2× of the data), or `001`/`010`
  on 1-replica Longhorn. The evaluation's disk estimate assumes the first.
- Operator via upstream chart vs vendored manifests (the OpenBao component chose local manifests to avoid
  `--enable-helm`; Velero and Zitadel use the generator).
- Bump cadence: monthly, gated by the `object-storage` use case, given the 2026-06 → 11 advisory wave.

Tests turning green: `object-storage` use case, Velero round-trip, image and ref pinning gates.

## Stage 4 — Overlays and external profile (one PR)

- Switch the six overlays using `minio/single-server` and the one using `minio/dev` to `storage/seaweedfs`
  (`single/` profile), with their buckets as CRDs and consumers wired through the contract.
- Generalise the external S3 profile: a short page (R2, B2, AWS) on supplying the contract Secret and declaring
  buckets with OpenTofu; `backup/velero/s3` links to it. Note the R2 limits (no versioning/Object Lock, presigned
  URLs only on the S3 endpoint, Velero ≥ 1.18.3).
- A page on the Rook-Ceph RGW path (`ObjectBucketClaim` → contract Secret), no component.

Tests turning green: every overlay builds; `stage-overlay-builds.sh`; use-case contracts.

## Stage 5 — MinIO deprecation and release (two PRs, one release apart)

1. Remove `./apps/minio` from `k8s/base/kustomization.yaml`; mark `minio/single-server` and `minio/dev`
   deprecated in the catalog (as `security/vault` was); release a **minor** version whose notes say the base no
   longer ships the MinIO operator and how to keep it until migration (pin the previous tag for the operator
   only, or vendor it in the tenant repo).
2. After the last known tenant migrates: delete `k8s/components/apps/minio/`, `docs/apps/minio.md` and the
   `base/minio` wiki page; recompile the wiki.

Order matters for tenants: delete the MinIO `Tenant` CR **before** bumping to the release without the operator,
otherwise the CR is left without a controller (finalizers) while Argo CD prunes the operator.

Tests turning green: base check.

## Stage 6 — First tenant migration: Scitrix (tenant repo, not this repo)

This repo ships a generic runbook, `docs/tenant-onboarding/migrating-from-minio.md`; the tenant's own steps,
hosts and credentials live in its repo. The runbook covers:

1. **Budget**: check disk and memory headroom for the new store next to MinIO (the evaluation estimates
   ≈7 GiB of disk for the first tenant's data instead of ≈22 GiB).
2. **Deploy** SeaweedFS (`small/` or `single/` profile) alongside MinIO; declare buckets, identities and policies
   as CRDs in git; one identity per application (no shared root keys).
3. **Copy** with rclone (`rclone sync minio: seaweed:` per bucket), verify object counts and checksums.
4. **Freeze** writers (suspend CronJobs, scale writers), final `rclone sync`, verify again.
5. **Cut over** each client to its contract Secret; during the window a Service named after the old one can point
   at the new S3 gateway so unchanged clients keep working.
6. **Watch** for an agreed period with MinIO read-only; keep the off-cluster mirror and Velero running.
7. **Remove** the MinIO `Tenant` and its PVCs, then bump the factory ref to the release without the operator.
8. **Agents**: replace the vendor MCP server with a vendor-neutral S3 MCP server using STS credentials (follow-up
   issue).

Then the other remote tenants and local overlays, in the order their owners choose.

## Follow-ups (separate issues)

- Vendor-neutral S3 MCP server for agents, with STS credentials.
- Spike: OpenBao AWS secrets engine (`openbao-plugins`, custom `sts_endpoint`) against SeaweedFS for dynamic keys.
- Adopt COSI when it ships v1beta1 and SeaweedFS's COSI driver follows.

## Risks

| Risk | Mitigation |
|---|---|
| SeaweedFS bus factor (one maintainer, ≈71 % of commits) | the contract keeps the store replaceable (Rook-Ceph or external S3) without touching applications |
| Advisory wave (57 GHSA 2026-06 → 11) | pin, monthly bump gated by the `object-storage` use case; subscribe to the repo's advisories |
| Enterprise-only features (admin audit log, EC repair) | not used; S3 audit log (OSS) is enough for the gates |
| Velero against SeaweedFS is not in Velero's provider list | the use case proves it; backups stay on an external S3 by default |
| Breaking change for remote tenants pinned to a tag | minor release with notes; tenants bump when they migrate |

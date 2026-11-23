# Object storage: MinIO replacement evaluation

Status: **accepted** (option A) · 2026-11-23 · Issue: [#72](https://github.com/AItizate/forjate/issues/72) ·
Plan: [`object-storage-plan.md`](object-storage-plan.md)

Every fact carries a source; all sources were read on 2026-11-23 unless another date is given. GitHub facts come
from `gh api`. "unverified" = not confirmed from a primary source. Licence verdicts are a triage, not legal advice.

**Decision (2026-11-23):** SeaweedFS with its operator as the default in-cluster store, behind an S3 contract;
external S3 (R2, B2, AWS) as a first-class profile; Rook-Ceph RGW for tenants with dedicated disks and nodes.

## 1. Current state

### MinIO in forjate (from `wiki/index.md`, compiled 2026-11-12)

| Piece | What | Consumers |
|---|---|---|
| `base/apps/minio` | MinIO **operator**, `resources: github.com/minio/operator` — **no `?ref=`**, floating | every overlay or remote tenant that composes `k8s/base` (remote tenants via `//k8s/base?ref=...`) |
| `components/apps/minio/single-server` | `Tenant` CR, image `quay.io/minio/minio:latest` (floating; **stopped resolving in 2026, 401**, recorded in `minio/dev/pod.yaml`, so a fresh pod cannot start) | 6 overlays: agentic-simple-workflow, ai-dev-stack, home-edge-lab, multi-cloud-portable, multi-tenant-pattern-org, usecases-invoice-intake-stages-walk |
| `components/apps/minio/dev` | bare Pod, `docker.io/bitnamilegacy/minio:2025.7.23` (frozen Bitnami legacy image) | usecases-invoice-intake |
| catalog capability | `artifact-store` is satisfied only by the two MinIO components | use-case builder (`data-store` expert) |

Components that hard-wire MinIO (also a breach of the component-independence rule in `CLAUDE.md`):

| Component | Coupling |
|---|---|
| `backup/velero` | default `values-minio-backend.yaml` targets the in-cluster MinIO component (`backup/velero/s3` is the external variant, already clean) |
| `communication/stalwart` | `endpoint = "http://minio:9000"` in the configmap; `kustomization.yaml` header says "MinIO (from k8s/base)" |
| `productivity/appflowy` | `http://minio:9000` in three Deployments (`appflowy-cloud`, `worker`, `ai`; `APPFLOWY_S3_MINIO_URL`, `AI_MINIO_URL`); `kustomization.yaml` header "MinIO (from k8s/base)"; S3 keys in its Secret |
| `databases/milvus` | `MINIO_ADDRESS=minio:9000`, `MINIO_ACCESS_KEY/SECRET_KEY=minioadmin` in the StatefulSet |
| `iac/crossplane` README, docs, builder plugin evals/fixtures/references | prose and golden records mention MinIO |

### First remote tenant (anonymised)

- 3 k3s nodes, 4 vCPU / 8 GiB each, memory at 54–62 % (about 3 GiB free per node); Longhorn disks of about
  97 GiB with **18–25 % free**, default replica count 2.
- MinIO Tenant from the archived operator: 1 server × 4 volumes on Longhorn, image `latest`.
- **3.3 GiB of objects, 6.6 GiB raw** (erasure coding on one server), on 2-replica Longhorn volumes: **about
  22 GiB of disk**, 6–7× amplification.
- Clients: a static site served by nginx from an anonymous-read bucket; a collaborative-docs app (avatars and
  blobs); a backend; a scraper CronJob; a weekly rclone mirror to an external S3. Velero already writes to an
  external S3 (kopia file-system backup).
- Buckets, users and policies are not declared in git (created by hand with `mc`).
- Another remote tenant also exposes MinIO to agents through the vendor's MCP server; the replacement needs a
  vendor-neutral S3 MCP server.

## 2. Why MinIO no longer works

| Fact | Date | Source |
|---|---|---|
| Licence Apache-2.0 → AGPL-3.0 | 2021-04-18 | github.com/minio/minio commit `0694325` |
| Admin console stripped from the community build (object browser only) | release `RELEASE.2025-05-24T17-08-30Z`, 2025-05-24 | minio/minio commit `160f8a9` (#21294); description: Blocks and Files 2025-06-19 (secondary) |
| Source-only distribution: no community binaries or images | 2025-10-15 (docs), 2025-10-18 (maintainer reply) | commit `9e49d5e`; issue #21647 |
| Last community release | `RELEASE.2025-10-15T17-29-55Z`, 2025-10-16 | minio/minio releases |
| README "maintenance mode" → "THIS REPOSITORY IS NO LONGER MAINTAINED", points to AIStor Free / Enterprise | 2025-12-03 → 2026-02-12 | commits `27742d4`, `be7800c`, `7aac2a2` |
| `minio/minio` archived (last push 2026-04-24); `minio/operator` archived (last push 2026-03-20), last releases v7.1.1 (2025-04-23), v5.0.18 (2025-05-05) | 2026 | `gh api repos/minio/{minio,operator}` |
| Unpatched in any community build: CVE-2026-41145 and CVE-2026-40344 (high, unauthenticated object write), CVE-2026-34204 (high, SSE metadata injection), CVE-2026-39414 (high, S3 Select DoS), CVE-2026-42600, -33322, -33419 (medium) | 2026-03 → 2026-04 | github.com/minio/minio/security/advisories |
| Bitnami images frozen in `bitnamilegacy` with no updates | 2025-08-28 | bitnami/containers #83267 |
| OpenSSF Scorecard minio/minio 5.1 | 2026-11-16 | api.securityscorecards.dev |

Forks: **pgsty/silo** (ex pgsty/minio, AGPL-3.0, last release 2026-11-12, 15 releases/12 m, one vendor) keeps
images and the console; **Chainguard** `cgr.dev/chainguard/minio` is AGPL, only `latest` free (pinning needs a paid
plan; partly unverified); **OpenMaxIO** dormant since 2025-06-24. None fixes governance or the AGPL.

## 3. Candidates

Legend for licence verdicts (internal / managed service / resale): G green, Y yellow, O orange, R red.
Baseline: **MinIO is R / R / R** (archived, unmaintained).

| | **SeaweedFS** (+ operator) | **Rook-Ceph RGW** | **Garage** | **RustFS** | **Versity S3 GW** | **Apache Ozone** | **External S3 (R2)** | MinIO fork (pgsty/silo) |
|---|---|---|---|---|---|---|---|---|
| Licence | Apache-2.0 (open core: Enterprise edition) | Rook Apache-2.0; Ceph LGPL-2.1/3 | **AGPL-3.0** | Apache-2.0 + **CLA allowing proprietary relicensing** | Apache-2.0 | Apache-2.0 | proprietary service | AGPL-3.0 |
| Verdict int/svc/resale | G / G / Y (single vendor, open core) | G / G / Y (Ceph LGPL, weak copyleft) | G / O / O | G / G / Y | G / G / Y | G / G / G | n/a (service contract; vendor lock) | G / O / O |
| Governance | single maintainer/vendor (Chris Lu) | **CNCF graduated 2020-10-07**; Ceph Foundation (LF) | Deuxfleurs collective (NLnet-funded) | single vendor (RustFS, Inc.) | single vendor (Versity) | **ASF top-level** | Cloudflare | single vendor (Pigsty) |
| Last release | 4.55, 2026-11-23; operator 1.0.46, 2026-11-23 | v1.21.2, 2026-11-05 (Ceph v20.2.4) | v2.5.0, 2026-10-24 | 1.0.6, 2026-11-15 (GA 1.0.0 2026-09-16) | v1.11.0, 2026-11-06 | 2.2.2, 2026-10-30 | — | 2026-11-12 |
| Releases / 12 m | 51 (operator 81) | 31 (two branches) | 6 | 59 | 14 | 6 | — | 15 |
| Contributors / top share | 401 / **71 %** | ≈725 / low | 101 / 65 % | 215 / 40 % | 89 / 59 % | 310 / 16 % | — | — |
| Scorecard | not indexed (operator 4.2) | **9.1** | none | not indexed | not indexed | 7.5 | — | — |
| Advisories | **57 GHSA, 2026-06→11** (19 crit, 24 high, 14 med; 32 in 2026-11) — active disclosure wave | Rook 0; Ceph 4 fixed in 20.2.4 (2026-08-19), 2 RGW without listed fix | 0 tracked (no GHSA DB); v2.5.0 security fixes | 43 GHSA (2025-12→2026-10); open data-loss issue #9509 | 10 (1 crit, 3 high) | 0 | — | inherits MinIO's |
| Declarative in git | **CRDs: Seaweed, Bucket, S3Identity, S3Credential, S3Policy, S3PolicyBinding, S3Role, S3OIDCProvider, BucketLifecyclePolicy**; Helm; COSI driver v0.5.0 | CephObjectStore, CephObjectStoreUser, **ObjectBucketClaim**; COSI driver experimental | Helm only; 3rd-party operator (GarageBucket, GarageKey), 10 months old | Tenant CRD only (operator v0.0.9) | Helm, no CRDs | Helm, no operator | Terraform/OpenTofu (`cloudflare` v5.29.0); Crossplane provider experimental, no releases | MinIO operator archived |
| IAM / bucket policy | IAM API + bucket policies | IAM + bucket policies | **no bucket policies** (per-key/bucket perms) | yes | yes | Ranger/ACLs | bucket-scoped tokens | yes |
| Short-lived creds (agents) | **STS: AssumeRole, AssumeRoleWithWebIdentity**, LDAP, GetFederationToken | **STS: AssumeRole, AssumeRoleWithWebIdentity** | **none** | STS AssumeRole/WebIdentity | WebIdentity only | AssumeRole (needs Kerberos + Ranger) | **Temporary Credentials API** (bucket/prefix, TTL) | yes |
| Encryption at rest | SSE-S3, SSE-KMS (**OpenBao/Vault**), SSE-C | SSE-S3, SSE-KMS (Vault only; OpenBao unverified), SSE-C | SSE-C only | SSE-KMS | delegated to FS | yes (TDE) | always on (Cloudflare keys) | yes |
| Audit | S3 audit log (OSS); admin audit = Enterprise | RGW ops log sidecar | not documented | yes | access log + webhooks | yes | data-access logs GA 2026-09-04 | yes |
| Versioning / lock | yes / yes | yes / yes | **no / no** | yes / yes | opt-in / yes | partial | **no versioning, no Object Lock** (bucket locks instead) | yes / yes |
| Velero | integration test in repo; not in Velero docs; one closed idle-connection issue (velero#9306) | listed "Ceph RADOS" (user-reported); `checksumAlgorithm: ""` | not documented | kopia restore bug #2721 (closed 2026-04) | not documented | not documented | works with Velero ≥1.18.3 / plugin ≥1.14.x (tagging fix, velero#9931); the first tenant runs it today | yes |
| Footprint | small: master/volume/filer/S3 can run in one process (exact minimum unverified) | **≈10 GiB RAM** minimum for 3 mon + mgr + 3 OSD + RGW (Rook minimums); OSDs need raw disks or block PVCs | 1 GiB RAM, 16 GiB disk | unverified | small (gateway over a filesystem) | heavy (JVM: OM, SCM, DN, S3G) | **zero in cluster** | small |
| arm64 / Pi | yes (multi-arch image incl. arm, arm64) | yes (but too heavy for a Pi) | yes (arm, arm64) | yes | yes | not for a Pi | n/a | yes |
| HA | replication per volume, filer metadata; EC (fixed ratio in OSS) | Ceph replication / EC, multisite | replication factor 3, ≥3 nodes | EC pools | none of its own | Ratis/Raft | provider | EC |

Not retained: **Zenko CloudServer** (user management needs proprietary Scality Vault, no OSS HA),
**JuiceFS gateway** (needs another object store behind it), **NooBaa** (Apache-2.0 but ≈6.5 GiB RAM before data,
Red Hat-paced, standalone weak), **CubeFS** (CNCF graduated, S3 via ObjectNode; not evaluated in depth — scout later
only if Rook is rejected), **OpenMaxIO** (dormant).

### Provisioning standards

| Standard | State | Source |
|---|---|---|
| **COSI** (kubernetes-sigs) | last release v0.2.2 (2025-12-08, v1alpha1); `main` on v1alpha2; KEP-1979 redesigned to v1beta1 on 2026-09-14, beta target v1.38 — **not production-ready** | repo tags; `kep.yaml` |
| **ObjectBucketClaim** (`lib-bucket-provisioner`) | README carries a deprecation notice, yet commits still land (2026-09-17); maintained in practice by Rook/NooBaa | repo |
| Crossplane `provider-upjet-aws` | v2.10.0, 2026-11-20 | releases |
| Crossplane `provider-upjet-cloudflare` | no releases, last commit 2026-06-02, template README — experimental | repo |

### Agent access (scoped, short-lived)

- STS `AssumeRoleWithWebIdentity` with a Kubernetes service-account token (OIDC) is the standard; SeaweedFS, Ceph RGW
  and RustFS implement it. Garage does not; R2 offers a Temporary Credentials API instead (broker pattern).
- OpenBao: the AWS secrets engine lives in `openbao/openbao-plugins` (`secrets-aws-v0.3.3`, 2026-11-04) and accepts
  custom `iam_endpoint`/`sts_endpoint`; whether it works against SeaweedFS or RGW is **unverified** (spike needed).
- One tenant's agent tool is the vendor AIStor MCP server; the replacement needs a vendor-neutral S3 MCP server.

## 4. Fit for the real products (first tenant and homelab)

| Criterion | SeaweedFS | External R2 | Rook-Ceph RGW |
|---|---|---|---|
| First tenant footprint (≈3 GiB RAM free per node, disks 18–25 % free) | fits in RAM (≈830Mi of requests). Disk: ≈7 GiB written once migrated (3.3 GiB data, Longhorn 2×, SeaweedFS `000`), but ≈24 GiB **provisioned** (master 1 + filer 1 + volume 10 GiB, × 2 replicas) and it must coexist with MinIO's ≈22 GiB during migration; on 2026-11-23 two of three Longhorn disks were **not schedulable** (below the 25 % minimum), so the migration is staged through external S3 unless disk is freed (plan, Stage 3) | frees ≈22 GiB and the operator | does **not** fit: ≈10 GiB RAM total, OSDs on Longhorn block PVCs = double replication |
| Homelab Pi | fits (arm64) | fits (needs internet) | does not fit |
| Buckets / users / policies in git | yes, CRDs (operator young: 1.0.x, 81 releases in 12 m) | via OpenTofu or immature Crossplane; outside Argo CD | yes (OBC, users); policies via S3 API |
| Agent creds | STS in cluster | broker over Temporary Credentials API | STS in cluster |
| Velero | target stays off-cluster anyway; SeaweedFS as target untested by Velero | proven on the first tenant today; note both forjate Velero values pin `velero-plugin-for-aws:v1.13.1`, below the R2 minimum above (plan, Stage 4) | user-reported |
| Migration from MinIO | `rclone copy -M` (rclone is already used for the off-cluster mirror) and `rclone check --download`; every client re-pointed to its contract Secret (no Service alias by default); new per-app keys | rclone copy; endpoints to R2; the static site must move to a public bucket or custom domain; app latency to a non-South-America location | same as SeaweedFS plus disks |
| Main risk | bus factor 71 %; advisory wave (57 in 6 months) → must pin and bump monthly | vendor lock, no versioning/Object Lock, no South America location, internet dependency | weight; operational complexity |

## Sources (read 2026-11-23)

github.com/minio/minio (commits 0694325, 160f8a9, 9e49d5e, 27742d4, be7800c, 7aac2a2; issue 21647; security
advisories; releases) · github.com/minio/operator · github.com/pgsty/silo · images.chainguard.dev/directory/image/minio ·
github.com/bitnami/containers/issues/83267 · blocksandfiles.com/2025/06/19/minio-removes-management-features-from-basic-community-edition-object-storage-code/ (secondary) ·
github.com/seaweedfs/seaweedfs (releases, security-advisories, wiki/Amazon-S3-API) · seaweedfs.com/docs/comparison/ ·
github.com/seaweedfs/seaweedfs-operator (config/crd/bases, releases) · hub.docker.com/r/chrislusf/seaweedfs ·
github.com/rook/rook (releases, Documentation) · raw.githubusercontent.com/cncf/landscape/master/landscape.yml ·
github.com/ceph/ceph/security/advisories · docs.ceph.com/en/latest/radosgw/STS/ · garagehq.deuxfleurs.fr (s3-compatibility, releases) ·
github.com/deuxfleurs-org/garage · github.com/rajsinghtech/garage-operator · github.com/rustfs/rustfs (README, CLA.md, SECURITY.md, #9509) ·
github.com/rustfs/operator · github.com/versity/versitygw (wiki) · github.com/scality/cloudserver · ozone.apache.org (release, STS docs) ·
github.com/juicedata/juicefs · github.com/noobaa/noobaa-core, noobaa-operator · github.com/kubernetes-sigs/container-object-storage-interface ·
github.com/kubernetes/enhancements keps/sig-storage/1979-object-storage-support · github.com/kube-object-storage/lib-bucket-provisioner ·
developers.cloudflare.com/r2 (api/s3/api, presigned-urls, pricing, bucket-locks, data-security, audit-logs, data-location, tokens, temporary-credentials) ·
registry.terraform.io/providers/cloudflare/cloudflare · github.com/crossplane-contrib/provider-upjet-cloudflare, provider-upjet-aws ·
github.com/velero-io/velero (releases 1.19.0 2026-11-23, issues 9931, 7940, 10584, 9963, 9306) · github.com/velero-io/velero-plugin-for-aws (v1.15.0) ·
velero.io/docs/main/supported-providers/ · github.com/openbao/openbao-plugins · api.securityscorecards.dev

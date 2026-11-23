# Object storage — MinIO replacement plan

Status: **proposed, revised after review** · 2026-11-23 · Issue: [#72](https://github.com/AItizate/forjate/issues/72) ·
Evaluation: [`object-storage-evaluation.md`](object-storage-evaluation.md)

## Scope

Replace MinIO in this factory with:

1. an **S3 object-store contract** that every consumer component reads, so no component names the store;
2. a **SeaweedFS component** (operator + store, pinned) as the default in-cluster implementation;
3. an **external S3 profile** (R2, B2, AWS) as a first-class alternative, generalising `backup/velero/s3`;
4. **Rook-Ceph RGW** documented as the path for tenants with dedicated disks and nodes (no component here);
5. removal of MinIO from `k8s/base`, then from `components/`.

The first remote tenant migrates first, then the others.

Out of scope in this repo: tenant-specific migration steps, hosts and credentials (they live in each tenant's
runbook, per the component-independence rule in `CLAUDE.md`), interim hardening of running MinIO instances, COSI
adoption (see Follow-ups).

## Why

MinIO's community edition is archived and unpatched (CVEs from 2026-03/04 are fixed only in the commercial AIStor),
the base pulls its archived operator without `?ref=`, and `quay.io/minio/minio:latest`, which
`minio/single-server` uses, stopped resolving in 2026 (401, recorded in `minio/dev/pod.yaml`): the six overlays
using it cannot start a fresh MinIO pod today. Four components hard-wire a `minio` host. Sources: the evaluation,
section 2.

## Decisions

These close the questions the first draft left open.

| # | Decision | Why |
|---|---|---|
| D1 | Contract keys are the **AWS SDK standard names** (see Contract) | SDKs read them without glue; a prefix works only through `envFrom.prefix`, which breaks SDK auto-discovery |
| D2 | One profile, `single/`: one master, one volume server, one filer, one S3 gateway; `defaultReplication: "000"`; durability from the tenant's StorageClass (Longhorn replica ≥ 2). **No `small/` profile** | three volume servers with `000` add RAM, not durability; `001` needs a non-replicated StorageClass the component cannot name |
| D3 | Operator installed with the Kustomize `helmCharts` generator (`includeCRDs: true`), like `backup/velero` and Zitadel. Argo CD `kustomize.buildOptions: --enable-helm` is a **documented prerequisite** checked in the migration budget step | upstream chart tracks the operator's 81 releases a year; vendoring would be re-done every month. the first tenant's Argo CD already runs with `--enable-helm` (read 2026-11-23); the factory's own `continuous-delivery/argocd` does not, and the component README says so |
| D4 | In-cluster S3 is **plain HTTP by default**, restricted by NetworkPolicy; TLS is an opt-in `tls/` sub-directory | a default `Certificate` would make the component require cert-manager (independence rule) and every consumer a CA |
| D5 | Filer metadata store: the operator default **`leveldb2` on the filer's own PVC** (1 GiB), no external database; metadata snapshots through the operator's `SeaweedBackup` CRD | lose the filer and every object is unreachable even if volume data survives |
| D6 | **Velero targets external S3.** SeaweedFS ships without a Velero-to-SeaweedFS guarantee; a round-trip against it is a nightly report, not a gate | that is what tenants run (the first tenant: Velero → R2 today); the gate would pull a privileged node-agent into a `restricted` use case |
| D7 | **STS for agents is a follow-up**, preceded by a spike; not part of the component's gate | no current tenant client needs it for the migration; k3d issuer discovery needs cluster-scoped RBAC that is not yet specified |
| D8 | SSE is **opt-in** until the key location and backup are documented | losing the SSE key loses the data; a header echo proves nothing |

## Principles

- **Test first, per PR.** Each stage PR's first commit adds the check that fails without the change; the PR merges
  when it is green. Repo-wide checks that must land before their offenders are fixed use a **committed baseline
  (ratchet)**: the check fails on a new offender and on a baseline entry that no longer offends, so the baseline
  only shrinks. There is no "expected failure" mode in this repo and none is added.
- **No stage leaves a local overlay broken on `main`.** A consumer is rewired in the same PR as every overlay that
  composes it (wiki `consumed_by`). Every tag between the rewiring and MinIO's removal carries upgrade notes per
  rewired component; tenants on `?ref=main` are warned in the PR and release notes.
- **Independence.** The contract is a convention (Secret shape + catalog wiring), not a component. No consumer
  references SeaweedFS; the SeaweedFS component knows nothing about its consumers.
- **Pinned, and checked.** Chart version and images are exact tags. The existing `ref-pinning-check.sh` and
  `image-policy-check.sh` only see use cases, so a new repo-wide pin check is added (Stage 1).
- **Scripts read the catalog.** No check names a component or a vendor.

## The contract

**Secret, one per consumer identity** (tenant-supplied, name chosen by the tenant, declared in the consumer's
catalog wiring):

| Key | Meaning |
|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the identity's keys, scoped to its buckets |

**Config, per binding** (ConfigMap or the same Secret, non-secret):

| Key | Meaning |
|---|---|
| `AWS_ENDPOINT_URL_S3` | full URL, e.g. `http://<service>.<ns>.svc:8333` |
| `S3_HOST`, `S3_PORT`, `S3_USE_TLS` | the same endpoint split, for clients that need `host:port` + a flag; the check asserts they agree with the URL |
| `AWS_REGION` | region (any value for in-cluster stores; `auto` for R2) |
| `S3_BUCKET` (or `S3_BUCKET_<ROLE>` for a consumer with several buckets) | bucket name(s) |
| `AWS_CA_BUNDLE` + `ca.crt` (optional) | only when the endpoint uses a private CA (opt-in `tls/`) |

A consumer with several buckets uses one identity Secret and several bucket keys, not several `envFrom` Secrets
with clashing `AWS_*` names. Path-style addressing is the documented default; there is no standard SDK variable for
it, so each consumer sets its own flag from the mapping below.

**Per-consumer mapping** (each verified in its stage; "unverified" items are checked first in that PR):

| Consumer | How it reads the contract |
|---|---|
| `databases/milvus` | `MINIO_ADDRESS` = `S3_HOST:S3_PORT`, `MINIO_USE_SSL` = `S3_USE_TLS`, `MINIO_ACCESS_KEY`/`SECRET_KEY` = `secretKeyRef` to the identity, bucket = `S3_BUCKET` (Milvus' own variable names, unverified for `MINIO_USE_SSL`/bucket). Alternative for the single local overlay: Milvus standalone with local storage, no S3 |
| `productivity/appflowy` | three Deployments (`appflowy-cloud`, `worker`, `ai`): `APPFLOWY_S3_USE_MINIO=true` and `AI_USE_MINIO=true` are the upstream switches for any custom endpoint; URL from `AWS_ENDPOINT_URL_S3`, keys by `secretKeyRef` |
| `communication/stalwart` | keys already `%{env:…}%`; endpoint `%{env:AWS_ENDPOINT_URL_S3}%` if Stalwart expands env there (unverified), otherwise the tenant patches the literal |
| `backup/velero` | `cloud` ini Secret (Velero's format) + `BackupStorageLocation` `s3Url`/`bucket`/`region` patched by the tenant; `caCert` when TLS |

**Catalog:** a new `object-store` capability in `wiki/catalog-capabilities.yaml` (carrying the contract key list),
in `docs/use-case-builder/contracts.md` (the vocabulary equality test requires both). Providers list
`object-store` and `artifact-store`. Consumers declare
`wiring.consumes: [{protocol: s3, secret: <name>, keys: [...], format: env | velero-cloud | config-file}]`; this is
new: `wiki-compile.py` rebuilds `wiring` from a fixed key set, so `merge_wiring` and `wiki/SCHEMA.md` learn it in
Stage 1 with a test in `test_builder.py`.

## Tracks

```
Track S (first tenant)        Track F (factory hygiene)
Stage 1 contract + checks ──┬─ Stage 4 rewire consumers + their overlays
Stage 2 SeaweedFS component ─┤ Stage 5 invoice-intake
Stage 3 first-tenant runbook ┘ Stage 6 builder plugin
     (migration runs in the     Stage 7 docs sweep
      tenant repo)              Stage 8 MinIO deprecation and removal
```

The first tenant's clients (static site, collaborative-docs app, backend, scraper, mirror job) use none of the four
rewired components, so its migration needs only Stages 1–3. Track F runs in parallel; Stage 8 comes last.

Each stage lists **Entry**, **Files**, **Exit** (commands) and **Owner**. Owner is the repo owner unless named.

## Stage 1 — Contract, catalog and repo-wide checks (one PR)

**Entry:** this plan merged.

**Files:**
- `docs/tenant-onboarding/configuring-object-storage.md` (new): the contract, the per-consumer mapping, and an
  "Implementations" section (SeaweedFS, external S3 with OpenTofu for buckets and tokens, Rook-Ceph via
  `ObjectBucketClaim` → contract Secret). `configuring-storage.md` (StorageClass/PV guide) stays and links to it.
- `wiki/catalog-capabilities.yaml`, `docs/use-case-builder/contracts.md`: `object-store`.
- `scripts/wiki-compile.py` (`merge_wiring` learns `consumes`), `wiki/SCHEMA.md`,
  `plugins/forjate/scripts/builder/tests/test_builder.py`.
- `wiki/catalog-overrides.yaml`: `object-store` added to `apps/minio/single-server` and `apps/minio/dev` (MinIO is
  the first contract provider, so the coupling exemption works from day one).
- `scripts/checks/object-store-coupling-check.sh` + `scripts/checks/object-store-coupling.baseline`: fails when a
  component *without* `object-store` carries a **value** matching a provider's catalog facts (`wiring.service`,
  `wiring.secret.name`, `wiring.label`, image repository) or a literal default credential. Application-owned env
  var **names** (`MINIO_ADDRESS`, `APPFLOWY_S3_USE_MINIO`) are allowed when the value comes from
  `secretKeyRef`/`configMapKeyRef`/`%{env:…}%`. Baseline today: velero (values, example, README), stalwart,
  appflowy (three Deployments), milvus, `iac/crossplane/README.md`.
- `scripts/checks/object-store-contract-check.sh`: for each consumer with `wiring.consumes`, the rendered pods'
  `secretKeyRef.key`s are a subset of the contract keys (reuses `scaffold-check.check_secret_keys`). In this stage
  it runs on schema (declarations are well-formed); Stage 4 adds the consumers and their rendered pods.
- `scripts/checks/pin-check.sh` + baseline: over `k8s/base/**` and `k8s/components/**` sources, fails on remote
  resources without `?ref=<tag|sha>`, `helmCharts` without an exact `version`, images `:latest` or untagged,
  including image fields of CRs the catalog marks operator-managed. Baseline today includes
  `base/apps/minio/operator` and `minio/single-server`.
- `.github/workflows/validate-kustomize.yml`: the three checks as named steps; a `kustomize build --enable-helm
  k8s/base` target; component discovery becomes "every directory under `k8s/components` with a
  `kustomization.yaml`" (today `-maxdepth 4` plus a hard-coded `velero/s3`).

**Exit:**
```
scripts/checks/object-store-coupling-check.sh   # 0, baseline unchanged
scripts/checks/object-store-contract-check.sh   # 0
scripts/checks/pin-check.sh                     # 0, baseline unchanged
poetry run pytest plugins/forjate/scripts/builder/tests
poetry run python scripts/wiki-compile.py && git diff --exit-code wiki/catalog.json  # after commit
```

## Stage 2 — SeaweedFS component and its use case (one PR)

**Entry:** Stage 1 merged. Spike done: render the operator's pods on k3d and run the PSA check (decides whether
the component can claim `restricted`).

**Files:** `k8s/components/apps/storage/seaweedfs/`:
- `kustomization.yaml`: namespace, label `ait-component: seaweedfs`, header (what it is, `--enable-helm`
  prerequisite, what the tenant patches: StorageClass, sizes, NetworkPolicy client label);
  `helmCharts` for the operator, pinned. Versions: chart `seaweedfs-operator-0.1.49`, operator `1.0.46`,
  SeaweedFS `4.55` (latest on 2026-11-23), or newer if an advisory requires it; the PR records date and reason.
- `seaweed.yaml`: the `Seaweed` CR, `single` shape (D2): `defaultReplication: "000"`,
  `volumeSizeLimitMB: 1024` (small volumes keep vacuum headroom low), standalone S3 gateway on port 8333 with
  embedded IAM, `podSecurityContext`/`containerSecurityContext` set per the spike, no WebDAV, SFTP, admin UI or
  Ingress. `storageClassName` left unset (tenant patch). PVC sizes: master 1 GiB, filer 1 GiB (D5), volume 10 GiB
  default (tenant patch from measured data × 2 for vacuum and growth).
- Resources (starting point, corrected from the use case's peak RSS report):

  | Pod | request | limit |
  |---|---|---|
  | operator | 64Mi | 256Mi |
  | master | 128Mi | 512Mi |
  | volume | 256Mi | 1Gi |
  | filer | 256Mi | 1Gi |
  | S3 gateway | 128Mi | 512Mi |
  | **total requests** | **≈830Mi** | |

- `networkpolicy.yaml`: S3 port admitted from namespaces labelled `forjate.io/object-store-client: "true"` (the
  tenant sets the label); internal ports only from the component's own pods.
- `tls/` (opt-in, D4): `Certificate` with a placeholder issuer, gateway HTTPS, notes per consumer (Velero `caCert`,
  `AWS_CA_BUNDLE`, nginx `proxy_ssl_trusted_certificate`).
- `examples/`: `Bucket`, `S3Identity` + `S3Credential`, `S3Policy` + `S3PolicyBinding` (bucket-scoped),
  `anonymous-read/` (one file; nginx proxies path-style `/<bucket>/` to the gateway), `SeaweedBackup` schedule
  (filer metadata snapshot), contract Secret + ConfigMap. Examples carry
  `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true` so the first sync does not fail before the
  CRDs exist.
- `README.md` and `docs/apps/seaweedfs.md`: the bump and exit policy (below), Enterprise-only features left out.
- `wiki/catalog-overrides.yaml`: `capabilities: [object-store, artifact-store]`, licence Apache-2.0, maturity
  `mvp`, PSA level from the spike, wiring (`service`, port 8333, `protocol: s3`).
- `k8s/overlays/usecases/object-storage/` (`isolation: dedicated`, it installs operator and CRDs): seed + verify
  Jobs. Verify proves, through the contract Secret only:
  1. a `Bucket` declared as a CRD is reachable;
  2. an identity scoped to bucket A writes A and is **denied** on B;
  3. presigned GET and PUT work;
  4. an anonymous-read bucket serves an object without credentials;
  5. a multipart upload larger than the part size round-trips;
  6. a metadata drill: delete the filer pod and its PVC, restore from the latest `SeaweedBackup`, list objects.

  Nightly report only (not a gate): Velero `backup/velero/s3` against the gateway as a stand-in S3 endpoint; peak
  RSS per pod.
- `.github/CODEOWNERS` (new): the component path and `docs/apps/seaweedfs.md` owned by the repo owner.

**Exit:**
```
kustomize build --enable-helm k8s/components/apps/storage/seaweedfs
scripts/checks/pin-check.sh
scripts/ephemeral/ephemeral.sh up object-storage   # verify Job exits 0
```

### SeaweedFS bump and exit policy

- **Owner:** the repo owner (CODEOWNERS), subscribed to advisories of `seaweedfs/seaweedfs` and
  `seaweedfs/seaweedfs-operator`. Optional scheduled workflow: compare pinned vs latest, list open GHSA.
- **Monthly** bump PR gated by the `object-storage` use case, then a patch tag.
- **Out of band:** a critical advisory, or a high one in S3/IAM/filer → bump PR and patch tag within 7 days; release
  notes flag security bumps; tenants may override the image tag in their overlay meanwhile.
- **Surface:** WebDAV, SFTP, admin UI and Ingress off by default.
- **Exit trigger** (any): a critical advisory unfixed upstream for 30 days; no release for 90 days; a licence or
  governance change; the operator archived. **Exit path:** the external-S3 profile through the same contract, with
  the Stage 3 runbook as the copy procedure. Each tenant keeps a store-neutral bucket list in its repo (bucket,
  owning app, anonymous flag) so the CRDs can be rewritten for another store.

## Stage 3 — First-tenant migration runbook (one PR here; execution in the tenant repo)

**Entry:** Stage 2 released (tag). **Files:** `docs/tenant-onboarding/migrating-from-minio.md`. **Owner of the
execution:** the tenant's operator, with a dated record in the tenant repo.

1. **Budget.** Read Longhorn `storage-minimal-available-percentage`, `storage-over-provisioning-percentage` and,
   per node, scheduled vs maximum and the `Schedulable` condition. Size SeaweedFS PVCs from measured data (object
   bytes × 2 for vacuum and growth). Confirm the PVCs × replicas schedule **while MinIO still holds its volumes**.
   Compare total requests (≈830Mi) with free memory per node. Check Argo CD `--enable-helm`. Never lower the Longhorn
   threshold as a workaround. On 2026-11-23 the first tenant had 2 of 3 Longhorn disks **not schedulable**
   (below the 25 % minimum), so it takes path B unless disk is freed first.
2. **Choose the path.**
   - **Path A (in place):** both stores fit. Steps 3–9.
   - **Path B (external staging):** they do not. (a) `rclone copy -M` MinIO → external S3 (the off-cluster mirror
     already holds most) and verify as in step 5; (b) cut clients over to the external-S3 profile; (c) delete the
     MinIO Tenant and PVCs (step 9 gates); (d) deploy SeaweedFS, copy external → SeaweedFS, verify; (e) cut clients
     over to SeaweedFS. Cost: two cutovers, latency to a store without a South-America location during the
     interval, and the static site needs a public external bucket or a custom domain meanwhile.
3. **Deploy** SeaweedFS next to MinIO; declare buckets, identities and policies as CRDs in git; one identity per
   application, no shared root keys; label client namespaces `forjate.io/object-store-client: "true"`; exclude
   the store's PVCs from Velero file-system backup (opt-out annotation), object-level DR is the mirror.
4. **Copy** per bucket with `rclone copy -M` (keeps Content-Type and Cache-Control; rclone streams, no local disk).
5. **Verify** per bucket: object count, total bytes, `rclone check --download` (full content compare; ETags and
   checksums differ across stores for multipart and SSE); Content-Type on a static-site sample; an anonymous GET
   through the site's nginx. Record output in the tenant runbook.
6. **Freeze and cut over.** Suspend writer CronJobs and scale writers; final `rclone copy -M`, verify again; re-point
   **every** client, including the mirror job, to its contract Secret and ConfigMap; restart. **No `minio` Service
   alias by default** (the operator owns that Service while the Tenant exists, ports differ, old keys would be
   refused). An alias only for a client that cannot be redeployed: created after the Tenant's Service is gone,
   mapping the old port, backed by a temporary bucket-scoped identity with the old key, in git with a removal date,
   deleted in step 9.
7. **Mirror.** At cutover the off-cluster mirror reads SeaweedFS, in `copy` mode (never `sync`) until step 9.
8. **Watch** for 14 days (the tenant runbook records owner and end date). MinIO keeps running, unreferenced.
9. **Point of no return**, each a separate commit: dated final copy `rclone copy minio: <external>:<bucket>-final-YYYYMMDD`,
   verified and kept 30 days → delete the MinIO `Tenant`; wait until `kubectl get tenants.minio.min.io -A` is
   empty and finalizers clear → delete the MinIO PVCs explicitly → bump the factory ref (Stage 8 notes).

## Stage 4 — Rewire consumers with their overlays (one PR per component)

**Entry:** Stage 2 merged. Each PR rewires one component **and** every overlay composing it, so no overlay is left
without a provider: the overlay switches to `storage/seaweedfs` (or keeps `minio/single-server` as the contract
provider until Stage 8 if switching is not possible yet) and supplies the contract Secret.

| PR | Files |
|---|---|
| Velero | parent becomes `resources: [./s3]` with one values file (release note: the in-cluster default is gone); `values-minio-backend.yaml`, `examples/backuplocation-minio.yaml` removed; `README.md`, `kustomization.yaml` header (also the missing `values-s3-backend.yaml` reference and `region: minio`); chart and `velero-plugin-for-aws` bumped to Velero ≥ 1.18.3 / plugin ≥ 1.14.x (evaluation minimums); `catalog-overrides.yaml` note; `consumes` |
| Stalwart | `configmap.yaml` endpoint, `kustomization.yaml` header; `consumes` |
| AppFlowy | `appflowy-cloud`, `worker`, `ai` Deployments, `kustomization.yaml` header; `consumes` |
| Milvus | `statefulset.yaml` (no default credentials); `catalog-overrides.yaml` note; overlay `ai-dev-stack/namespaces/dev` (also its `minio-storage-configuration-patch.yaml` and `configs/node-red-flows.json`) |
| Other overlays on `minio/single-server` | `agentic-simple-workflow` (`agent-deployment.yaml`), `home-edge-lab` (`validate-job.yaml` probes `/minio/health/live`), `multi-cloud-portable`, `multi-tenant-pattern/org`, `usecases/invoice-intake/stages/walk` (with Stage 5), their READMEs |

**Exit:** coupling baseline shrinks by the PR's entries; contract check covers the rewired consumers' rendered
pods; `scripts/gates/checks/stage-overlay-builds.sh` and the `validate-kustomize` workflow green.

## Stage 5 — invoice-intake (one PR)

About 130 MinIO references in 27 files. Port `app/` to a generic S3 client reading the contract keys (or state that
the `minio` Python client stays as a generic S3 client), drop the `minio` Service alias, reseal the walk-stage
Secret, retarget NetworkPolicies, regenerate `.builder/` through the builder, switch `minio/dev` → SeaweedFS
`single/`. **Exit:** `validate-usecases` green; nightly e2e green on the next run.

## Stage 6 — Builder plugin (one PR)

`skills/kustomize/scripts/assemble.py` (hard-coded `MINIO_ROOT_*`), `scaffold-check.py`, `skill-lint.py`,
`tests/test_builder.py`, `tests/test_gates.py`, `skills/app-scaffold/SKILL.md`, `skills/*/references`, evals
(`compliance/evals.json` re-anchors its AGPL premise on another AGPL component in the catalog;
`ai-engineering`, `data-store`) and fixtures (`packs/us-only`, `records`, `decisions`, `gates`, `scaffold`).
Golden records regenerated after Stage 2 exists. **Exit:** `poetry run pytest plugins/forjate/scripts/builder/tests`,
`claude plugin validate ./plugins/forjate`.

## Stage 7 — Docs sweep (one PR)

Rule: every file that the coupling check or `rg -i minio` lists outside the store components is handled in the
stage that rewires it; what remains is prose, handled here: `CLAUDE.md`, `README.md`, `docs/apps/{minio,longhorn,
lancedb,node-red,appflowy,affine}.md` (`affine.md` documents wiring the component lacks), `docs/service-integration.md`,
`docs/overlays/*.md`, `docs/assets/architecture/*.prompt.md`, `docs/use-case-builder/plan.md`,
`docs/ephemeral-use-cases.md`, `docs/lab-to-production.md`, `docs/agentic-reference-architecture.md`,
`k8s/components/apps/iac/crossplane/README.md`, `.github/workflows/usecase-e2e-nightly.yml` comment. Historical
benchmark records under `docs/use-case-builder/benchmarks/` stay as they are. **Exit:** `rg -i minio` outside the
store components, the deprecation notes and historical records returns nothing.

## Stage 8 — MinIO deprecation and removal (three PRs, releases apart)

1. **Deprecate.** Pin the base operator: `github.com/minio/operator?ref=v7.1.1` (the version in use) so it stops
   floating; set `argocd.argoproj.io/sync-options: Prune=false` on the MinIO CRDs; in `catalog-overrides.yaml`
   set `stages: []` and remove `artifact-store`/`object-store` from `apps/minio/single-server` and `apps/minio/dev`;
   DEPRECATED header in both kustomizations and an authored wiki summary (as `security/vault` has). Release.
2. **Remove from base** (minor release). Notes and a snippet: *commit A removes the Tenant; wait until
   `kubectl get tenants.minio.min.io -A` is empty and finalizers clear; delete PVCs explicitly; commit B bumps the
   factory ref. A tenant that keeps MinIO adds the pinned operator (`//k8s/base/apps/minio?ref=<last tag>` or
   vendored) in the same commit as the bump. Leftover CRDs (Prune=false) need a manual `kubectl delete crd`.*
3. **Delete** after the last known tenant migrates: `k8s/components/apps/minio/`, `docs/apps/minio.md`, the
   `base/minio` wiki page, the coupling baseline entries; update the authored `wiki/concepts/multi-tenant-recursion.md`.

**Exit (2):** `kustomize build --enable-helm k8s/base | yq 'select(.apiVersion | test("minio.min.io"))'` is empty;
`pin-check.sh` baseline loses the base entry.

## Rollback points

| Point | How |
|---|---|
| Stages 1, 2, 4–7 | revert the PR |
| Stage 8.1 / 8.2 | re-add the pinned operator to base in a patch release |
| R0 — before cutover (Stage 3 steps 3–5) | delete the SeaweedFS namespace; MinIO untouched |
| R1 — watch period (step 8) | freeze writers → `rclone copy -M seaweed: minio:` for objects written since cutover → switch contract Secrets back → unfreeze; MinIO kept running and unreferenced for exactly this |
| R2 — point of no return (step 9) | none after the PVCs are deleted; the dated final copy on external S3 (kept 30 days) is the recovery source |

## Follow-ups (separate issues)

- **STS spike, then a vendor-neutral S3 MCP server for agents** (D7): Kubernetes API server as OIDC issuer for the
  gateway (`S3OIDCProvider`), issuer discovery RBAC (cluster-scoped binding, `isolation: dedicated`), projected
  token audience and `expirationSeconds`; checks: `Expiration ≤ requested + 60 s`, wrong audience denied, real
  expiry nightly. Replaces the vendor MCP server another tenant runs today.
- OpenBao AWS secrets engine (`openbao-plugins`, custom `sts_endpoint`) against SeaweedFS for dynamic keys.
- SSE (D8): key location, backup and an at-rest assertion (a stored chunk is not plaintext).
- Adopt COSI when it ships v1beta1 and SeaweedFS's COSI driver follows.

## Risks

| Risk | Mitigation |
|---|---|
| SeaweedFS bus factor (one maintainer, ≈71 % of commits) | contract keeps applications store-neutral; exit trigger and path in the bump policy; store-neutral bucket list per tenant |
| Advisory wave (57 GHSA 2026-06 → 11) | bump policy: monthly plus 7-day out-of-band; reduced surface |
| Filer metadata loss | own PVC on replicated storage, scheduled `SeaweedBackup`, drill in the use case |
| First tenant's disks cannot host both stores | budget step; path B (external staging) |
| Enterprise-only features (admin audit log, EC repair) | not used |
| Velero against SeaweedFS not in Velero's provider list | Velero targets external S3 (D6); nightly report only |
| Breaking changes for tenants bumping their ref | upgrade notes on every tag from Stage 4 to Stage 8; Stage 8 snippet |

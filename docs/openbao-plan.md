# `security/openbao` component — implementation plan

Status: **proposed** · 2026-10-25

## Scope

Add `k8s/components/apps/security/openbao/`: an OpenBao secret store that any tenant can
activate, plus everything inside this repo that has to know about it — the External
Secrets store that points at it, docs and wiki.

Branches from `main`. The use-case builder (`plugins/forjate`, `wiki/catalog-overrides.yaml`,
`overlays/usecases/**`) lives on the unmerged `feat/use-case-builder` branch; its
integration is a follow-up once that branch lands (see the end of this plan).

Out of scope: any tenant's deployment, exposure or host configuration. Tenants patch
hostnames, storage class, sizing and unseal mode in their own overlays.

## Why a new component instead of fixing `security/vault`

`security/vault` ships `hashicorp/vault:1.19` (BUSL-1.1), `storage "file"`,
`tls_disable = 1`, an Ingress on the plain-HTTP `web` entrypoint, no audit device and no
unseal story. It has no consumer. On `feat/use-case-builder`, the builder's security
expert already rejects it on licence grounds.

OpenBao is MPL-2.0 under the Linux Foundation, and its API is the same as Vault's. ESO's
`vault` provider, the Vault Terraform provider and `vault:`-style references keep working.
It adds what the old component lacks: raft storage, static-key auto-unseal, an SSH CA,
Kubernetes auth and audit devices, with no enterprise tier.

## Component layout

Local manifests, not the upstream Helm chart. The chart's injector and CSI provider are
not needed, and plain manifests build without `--enable-helm`. The shape follows
`databases/postgres` (see `wiki/concepts/component-anatomy.md`).

```
k8s/components/apps/security/openbao/
├── kustomization.yaml       # namespace security, label ait-component: openbao,
│                            # header comment: what it is, unseal modes, what to patch
├── serviceaccount.yaml
├── rbac.yaml                # ClusterRoleBinding system:auth-delegator (kubernetes auth)
├── configmap.yaml           # openbao.hcl
├── service.yaml             # ClusterIP 8200
├── service-internal.yaml    # headless, 8200/8201, for raft peers
├── statefulset.yaml
├── networkpolicy.yaml       # ingress to 8200 only from labelled namespaces
├── ingress.yaml             # openbao.example.com, entrypoint websecure only
├── policies/                # HCL policy templates, applied by scripts/openbao/bootstrap.sh
│   ├── admin.hcl
│   ├── external-secrets.hcl # read kv/data/workloads/*
│   ├── agent.hcl            # one template for every agent (k8s ServiceAccount or AppRole): read kv/data/agents/<name>/*, update ssh-client/sign/agent; bootstrap.sh renders the mount accessors in
│   ├── agent-onboarding.hcl # registers agents: writes kv/agents/*, manages approle roles agent-* that can only carry the agent policy
│   └── raft-snapshot.hcl    # read sys/storage/raft/snapshot (raft-snapshot token)
├── seal-static/             # optional sub-component
│   ├── kustomization.yaml
│   └── patch-seal.yaml      # adds seal "static" to the config, mounts the key Secret
├── raft-snapshot/           # optional sub-component
│   ├── kustomization.yaml
│   ├── cronjob.yaml         # bao operator raft snapshot save → PVC, every 6 h
│   └── pvc.yaml             # tenants patch the storage class or the volume
└── eso-store/               # optional sub-component, requires security/external-secrets
    ├── kustomization.yaml
    └── clustersecretstore.yaml
```

### `openbao.hcl`

```hcl
ui            = true
disable_mlock = true

listener "tcp" {
  address         = "[::]:8200"
  cluster_address = "[::]:8201"
  tls_disable     = 1          # TLS terminates at Traefik; NetworkPolicy limits who can reach 8200
  telemetry { unauthenticated_metrics_access = true }
}

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-0"
}

api_addr     = "http://openbao.security.svc:8200"
cluster_addr = "http://openbao-0.openbao-internal.security.svc:8201"

audit "file" "stdout" { options { file_path = "stdout" } }   # declarative: the API refuses to create audit devices

telemetry { prometheus_retention_time = "30s", disable_hostname = true }
```

Single node by default. HA (3 replicas, `retry_join`) is a tenant patch, with an example in
the docs. It is not a fourth sub-component until something actually consumes it.

### `statefulset.yaml`

- Image `quay.io/openbao/openbao:<x.y.z>`, pinned to the latest **stable** 2.x when the
  work is done (2.7 was still beta in September 2026). It is multi-arch (amd64/arm64).
- Restricted Pod Security: `runAsNonRoot`, `readOnlyRootFilesystem`, all capabilities
  dropped, `seccompProfile: RuntimeDefault`. `disable_mlock` removes the need for `IPC_LOCK`.
- Requests 50m / 64Mi, limits 500m / 192Mi. Small enough for an edge node; tenants
  patch it upward.
- PVC template of 1Gi with no `storageClassName` (the tenant picks one; the docs say raft
  needs block or local storage, **not NFS**).
- Readiness probe `/v1/sys/health?standbyok=true&sealedcode=204&uninitcode=204`. Liveness
  uses the same path but tolerates sealed, so a sealed pod is not restart-looped.

### Unseal modes

| Mode | How | Trade-off |
|---|---|---|
| Shamir (default) | `bao operator init` → key shares kept offline; `bao operator unseal` after every restart | Strongest at rest; needs a human after each restart |
| `seal-static` | 32-byte key in Secret `openbao-seal-key`, read via `file://` at start | Unattended restarts; the key lives in the cluster. The tenant supplies the Secret (SealedSecret or out of band); the component never ships one |

The sub-component also mounts an optional `previous` key, so key rotation works as the
OpenBao docs describe.

### `eso-store/clustersecretstore.yaml`

```yaml
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: openbao              # patchable: invoice-intake expects "corporate-store"
spec:
  provider:
    vault:
      server: http://openbao.security.svc:8200
      path: kv
      version: v2
      auth:
        kubernetes:
          mountPath: kubernetes
          role: external-secrets
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

### `scripts/openbao/bootstrap.sh`

The component deploys the server. Configuring it needs an admin token, so it cannot be a
manifest. The script is idempotent and run once by a human after `init`:

1. enable `kv-v2` at `kv/`
2. enable `kubernetes` auth and create role `external-secrets`, bound to ESO's ServiceAccount
2b. enable `approle` auth for agents outside the cluster, and a kubernetes role `agent` for any ServiceAccount of the agents namespace (no per-agent setup)
3. enable `ssh` at `ssh-client/`, generate the CA and create role `agent` (TTL 30m, max 1h, principals passed as arguments)
4. check that an audit device is enabled (it is declared in `openbao.hcl`; OpenBao refuses to create one through the API) and fail loudly at the end if not
5. write every file under `policies/`

It prints nothing secret except the SSH CA **public** key that hosts need.

## Changes elsewhere in forjate

| File | Change |
|---|---|
| `docs/apps/openbao.md` | Install, init, both unseal modes, bootstrap, backup/restore, HA patch, rotation |
| `docs/tenant-onboarding/agent-secrets.md` | **Written** (with step 4): agents inside and outside the cluster, scoped kv reads, short-lived SSH certificates, lifecycle |
| `wiki/concepts/secret-strategy.md` | Add the store as a fifth entry and state the recommended pairing (external-secrets syncing from openbao) |
| `security/vault` | Header comment and docs: deprecated in favour of `openbao`. Removal is decided after the builder integration (open points) |

## Steps

| # | Work | Done when |
|---|---|---|
| 1 | Base component (config, StatefulSet, Services, RBAC, NetworkPolicy, Ingress) | `kustomize build` is clean; kubeconform passes; on k3d, `init` + `unseal` work and the pod passes PSA `restricted` |
| 2 | `seal-static` | On k3d: delete the pod → it comes back unsealed by itself; rotation with a `previous` key works |
| 3 | `raft-snapshot` | Snapshot written → PVC wiped → `bao operator raft snapshot restore` → data back |
| 4 | `bootstrap.sh` + `policies/` | Running it twice changes nothing the second time; the `agent` token can read only its path and sign a cert that expires |
| 5 | `eso-store` | On k3d with `security/external-secrets`: an ExternalSecret on `v1` syncs from `kv/workloads/demo` |
| 6 | Ephemeral use case `openbao-secrets` + CI | `ephemeral.sh up openbao-secrets` exits 0 from a clean machine and `validate-usecases.yml` runs it (see below) |
| 7 | Docs + wiki | `scripts/wiki-compile.py` run; `wiki-lint.py` clean; no secret value anywhere under `wiki/` |
| 8 | Release `v1.2.0-rc.1` | Tag pushed per `docs/release-process.md`; a consumer validates it before `v1.2.0` |

Steps 1–7 make up this branch's PR.

### Step 6 — the full environment test is part of `validate`

Steps 1–5 are proved by hand on a k3d. That does not survive the branch: nothing in CI
would notice if `bootstrap.sh`, a policy or `eso-store` broke. Forjate already has the
mechanism (`docs/ephemeral-use-cases.md`), so the proof becomes a use case:

`k8s/overlays/usecases/openbao-secrets/` with a `usecase.yaml` contract, composing
`security/openbao` + `seal-static` + `raft-snapshot` + `eso-store` + `security/external-secrets`.

| Job | Does |
|---|---|
| `seed` | `bao operator init`, creates the seal key and the snapshot token, runs `bootstrap.sh`, writes `kv/workloads/demo` and `kv/agents/<agent>/…` |
| `run` | runs `bootstrap.sh` a second time and compares the configuration before and after |
| `verify` | exits 0 only if: an `ExternalSecret` on `v1` syncs `kv/workloads/demo`; a k8s agent (ServiceAccount in `agents`, from a pod in a namespace labelled `openbao-access`) and an AppRole agent each read their own path, are denied another agent's path and `workloads/`, and get a certificate whose validity is ≤ 1h (a `ttl=24h` request is refused); `agent-onboarding` cannot create a role with another policy; a snapshot is taken, the data PVC is wiped, the restore brings the data back |

CI: add `openbao-secrets` to the `e2e-smoke` job of `validate-usecases.yml`, which today
only brings up `db-migration-a-to-b`. The contract lint, `shellcheck` (add
`scripts/openbao/bootstrap.sh`, with `-s sh`) and `validate-kustomize.yml` already pick the
new files up by path. Adjacent fixes on `main` (ESO `v1beta1`, ArgoCD `--enable-helm`) are
not needed: the use case builds its own manifests.

## Adjacent fixes on `main` (separate PRs, not part of this component)

Found while reading the tree. Both get in the way of the `eso-store` path in practice:

- `security/external-secrets/kustomization.yaml`: the header example is on
  `external-secrets.io/v1beta1`, which ESO ≥ 0.17 (chart 2.3.0 here) no longer serves.
- `continuous-delivery/argocd`: no `kustomize.buildOptions: --enable-helm`, so an ArgoCD
  from this component cannot render `external-secrets`.

## Follow-up after `feat/use-case-builder` merges

Not on `main` yet, so not part of this branch:

| File | Change |
|---|---|
| `wiki/catalog-overrides.yaml` | New `apps/security/openbao`: stages `[walk, run]`, roles `[secret-store, pki, ssh-ca]`, `psa_restricted: true`, licence `MPL-2.0`, maturity `lab` |
| `plugins/forjate/scripts/builder/validate.py` | **Design point**: `EXCLUSIVE_GROUPS["secrets mechanism"]` puts `vault` beside `external-secrets` as mutually exclusive, but a store and the operator that syncs from it are used together. OpenBao must **not** join that group. It pairs with `external-secrets` and is excluded only by `security/vault`, in a new `secret store` group |
| `plugins/forjate/scripts/builder/schemas/constraints.schema.json` | Nothing new in the `secrets_mechanism` enum; a pack names the store through the component, not the mechanism |
| `plugins/forjate/skills/security/SKILL.md` + `references/secrets-ladder.md` | At Run: `external-secrets` + `openbao` when the org has no store of its own; drop the "Vault is BUSL" caveat from that path |
| `plugins/forjate/skills/compliance/references/licences-and-providers.md` | Add `apps/security/openbao` — MPL-2.0, **ok** |
| `plugins/forjate/evals/{security,devops}` | One case each: Run picks external-secrets + openbao with no conflict |
| `overlays/usecases/invoice-intake/stages/run` | **Bug**: nine ExternalSecrets on `v1beta1`, which fail on apply with chart 2.3.0. CI misses it because kubeconform runs with `-ignore-missing-schemas` and nothing applies |

Done when `poetry run pytest plugins/forjate/scripts/builder/tests` is green, the new
evals pass, and `claude plugin validate ./plugins/forjate` is clean.

## Open points

- **Remove or keep `security/vault`** after deprecation: on `feat/use-case-builder`, the
  builder evals and the `flux-shop` fixture pack reference it, so removing it touches the
  plugin too.
- **Ship a `lite` ESO variant** (no webhook, no cert-controller) for small nodes? It
  belongs to `security/external-secrets`, not here, but `eso-store` documents the pairing.
- **MCP server**: not in v1. The CLI plus the `agent` policy covers the case with less surface.

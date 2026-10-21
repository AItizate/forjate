# Patterns from a real tenant (im-u)

Survey of `im-u/iac`, a production tenant that consumes this factory by SSH refs, done 2026-10-03 to ground the builder's skills in what a tenant actually does rather than what the convention says. Facts only; each line names where it was observed. Skills that must read this: `kustomize`, `security`, `devops`, `data-store`, `architecture`, `stage-planner`.

## What a tenant root looks like

No `base/`, no `overlays/`, no environment directories. One root `k8s/kustomization.yaml` pulls the factory base remotely and composes namespace sub-overlays:

```yaml
resources:
  - ssh://git@github.com/AItizate/tenant-iac-factory.git//k8s/base?ref=v1.9.0-rc.1
  - ssh://git@github.com/AItizate/tenant-iac-factory.git//k8s/components/apps/sealed-secrets?ref=v1.4.1
  - ./namespaces/default
  - ./namespaces/security
labels:
  - pairs:
      app.kubernetes.io/managed-by: kustomize
      app.kubernetes.io/overlay: im-u.com
```

- `k8s/patches/` holds cross-namespace infra patches (Longhorn settings, Traefik, oauth2-proxy middlewares, a global `storageClassName` patch targeting every PVC).
- `k8s/namespaces/<ns>/` has `kustomization.yaml` plus optional `patches/`, `secrets/`, `configs/`, `middlewares/`. Eleven namespaces; one (`cert-manager`) is a dead directory not referenced from the root.
- App repos ship their own `k8s/base/` and are consumed by SSH ref; the tenant overlay owns no app manifests.
- Naming: patches `<app>-<concern>-patch.yaml`; secrets `sealed-<name>.yaml`, `<name>.env`, `<name>.env.example`; local resources `<app>-ingress.yaml`, `<app>-certificate.yaml`, `<app>-init-job.yaml`.

## Remote references

Two URL shapes coexist: `.git//k8s/...` (double slash) for factory subdirectories, `.git/k8s/base` (single slash) for sibling app repos. Pinning is not uniform: across the tree `v1.4.0` ×14, `v1.9.0-rc.1` ×7, `v1.4.1` ×2, `v1.5.1` ×1, plus **branches** (`feat/add-zitadel-auth` ×3, `develop` ×3, `main` ×1). Five factory versions live side by side. Bundles are chosen explicitly to cut clone cost (`# Temporal workflow engine + PostgreSQL (single bundle = 1 SSH clone)`).

## Secrets

**Sealed Secrets only**: 24 `sealed-*.yaml` under `namespaces/*/secrets/`; no `secretGenerator`, External Secrets, Vault or sops. `metadata.name` equals the target Secret name; namespace repeated in `metadata` and `spec.template.metadata`; `sealedsecrets.bitnami.com/cluster-wide: "true"` only on the registry credential.

`.env.example` exists for 2 of 24 secrets. Where it exists, the sealing recipe is a comment header:

```
# Formbricks secrets -- replace values before sealing
# To generate: openssl rand -hex 32
# To seal: convert-to-sealed-secret.sh formbricks-secret.env productivity
DATABASE_URL=postgresql://formbricks:CHANGE_ME@postgres:5432/formbricks
```

Rotation and re-sealing are not scripted; they appear only as commit messages. **Two LLM API keys are committed in plaintext**, one in a `configMapGenerator` literal and one in an env patch. This is the single most important finding for the security skill.

The factory placeholder Secret is removed with the most repeated patch in the tenant (11 times):

```yaml
- target: { kind: Secret, name: postgres-secret }
  patch: |
    $patch: delete
    apiVersion: v1
    kind: Secret
    metadata:
      name: postgres-secret
```

## Patches

Dominant idiom: `path:` + `target: {kind, name[, namespace]}`. Inline `patch: |` is reserved for `$patch: delete` and short JSON6902 ops. Recurring shapes:

- hostname: `replace /spec/rules/0/host`, or a full strategic-merge Ingress for multi-host
- storage: `/spec/volumeClaimTemplates/0/spec/storageClassName: longhorn`, plus the global PVC patch
- `replicas: 0` with `# Temporarily scaled to 0 — hardware constraints`
- `nodeSelector` on a tenant label (`im-u.com/cpu-arch: v1`); image downgrade with a reason (`nodes lack AVX for mongo 7`)
- Traefik middleware chain annotation with `~1` escaping
- `imagePullSecrets` on every ServiceAccount (`target: {kind: ServiceAccount}`, no name)
- `labelSelector` targeting (`app.kubernetes.io/part-of=zitadel-stack`) to force `metadata.namespace` on Helm-rendered output
- index-based JSON6902 into `env` arrays of init containers, each with a comment naming the ordering it depends on; the main breakage point on upgrades

## Namespaces and hardening

`namespace.yaml` exists in 6 of 11 namespaces, bare, no labels. Each sub-overlay sets `namespace: <ns>` globally (the convention warns against it at the root; it works at sub-overlay level because the factory base declares its own namespaces). **Absent in the whole tenant: PSA labels, NetworkPolicies, `securityContext`, probes.** Requests and limits exist on the tenant's own app Deployments.

## GitOps and CI

One ArgoCD `Application`, `targetRevision` on a feature branch, `automated: { prune: false, selfHeal: false }`, `ServerSideApply=true`. No ApplicationSet, no sync waves. SSH refs require the repo-server wiring: `argocd-ssh-keys` mounted at `/app/ssh-keys`, `GIT_SSH_COMMAND: ssh -F /app/ssh-keys/ssh_config`, `reposerver.enable.kustomize.helm: "true"`, 600 s timeouts.

Image write-back: a consumer repo fires `repository_dispatch: update-image-tag`; the workflow runs `yq -i '(.images[] | select(.name == "<image>")).newTag = "<sha>"'` on the namespace kustomization and commits `chore(deploy): update <app> to <sha> in <env>` with `concurrency: gitops-<env>-<app>`. Tags are full SHAs. `testing` and `production` resolve to the same directory: one environment in practice.

## Versus `docs/overlays/CONVENTION.md`

Contradicts: Mínimo 2–6 (README, design doc, diagram, prompt, index) absent; Recommended 7 (global `namespace:`) used at sub-overlay level; 9 and 10 (probes, restricted `securityContext`) absent; Advanced 13 (`.env.example` for every `.env`) 2 of 24; 14 and 15 (bootstrap scripts, validation Job) absent, though init Jobs exist with `ttlSecondsAfterFinished` and `backoffLimit`, not suspended, asserting nothing. Extends the convention with everything under Remote references, Secrets and Patches above.

## Lessons, by skill

| # | Skill | Lesson |
|---|-------|--------|
| 1 | kustomize | Teach the tenant-root shape: remote factory base + `./namespaces/<ns>` children + root `labels.pairs` with `app.kubernetes.io/overlay: <tenant>`. Real tenants have no `base/` + `overlays/` split. |
| 2 | kustomize | Document both SSH URL forms and require `?ref=<tag>`; flag branch refs as drift. |
| 3 | kustomize | Add the `$patch: delete` recipe for replacing a factory placeholder Secret with a SealedSecret of the same name. |
| 4 | kustomize | Standardise `<app>-<concern>-patch.yaml` registered by `path` + `target`; inline `patch:` only for deletes and ≤3-line JSON6902 ops. |
| 5 | kustomize | Index-based JSON6902 into `env` arrays must carry a comment naming the assumed ordering, and should be replaced by strategic-merge on `name` where possible. |
| 6 | kustomize, architecture | Prefer `bundles/*` over several `apps/*` refs that land in one namespace; one SSH clone per resource entry. |
| 7 | data-store | `storageClassName` is a first-class overlay parameter: one global PVC patch plus per-StatefulSet `volumeClaimTemplates/0` patches. |
| 8 | data-store | Ship init Jobs for multi-database Postgres and Mongo (`POSTGRES_MULTIPLE_DATABASES`, `init-mongo.js` via `configMapGenerator` with `disableNameSuffixHash`) as a named pattern. |
| 9 | security, kustomize | Every sealed secret needs a `.env.example` beside it with the generate and seal commands in its header; the skill emits the missing ones. |
| 10 | security | Scan `configMapGenerator.literals` and env patches for plaintext credentials; the real tenant leaks two LLM keys this way. A `ci` gate, not a note. |
| 11 | devops, architecture | Record the ArgoCD prerequisites for SSH-ref overlays (repo-server SSH keys volume, `GIT_SSH_COMMAND`, Helm enabled, 600 s timeouts) as part of any overlay that references private components. |
| 12 | devops, stage-planner | Encode the honest environment model: image write-back by `repository_dispatch` + `yq` into `images:`; "testing and production resolve to the same directory" is the gap Walk is supposed to close. |
| 13 | security, kustomize | PSA labels, a default-deny NetworkPolicy per namespace and restricted `securityContext` are absent from a production tenant, so the skills generate them unprompted from Walk rather than list them as optional hardening. |
| 14 | devops | Sealed-secret rotation needs a script and a gate; today it exists only as commit messages. |
| 15 | security | `automated: { prune: false, selfHeal: false }` on a branch `targetRevision` is a Crawl posture; the devops record names the Walk posture (tag, `selfHeal: true`, prune after a dry run). |

Also observed: `im-u/iac/CLAUDE.md` describes a `gitops/{production,testing}/<app>.yaml` tree that does not exist. Documentation drift in the tenant itself; the coordinator's review mode should compare a tenant's `CLAUDE.md` with its tree before trusting either.

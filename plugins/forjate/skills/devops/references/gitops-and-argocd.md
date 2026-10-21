# GitOps with ArgoCD

## Sync posture per stage

| Stage | `argocd_sync` | `target_revision` | Why |
|-------|---------------|-------------------|-----|
| Crawl | `n/a` | `branch` (the runner applies the working tree) | nothing is reconciled; the TTL is the lifecycle |
| Walk | `auto-selfheal` (`automated: { selfHeal: true, prune: false }`) | `tag` | drift is corrected, nothing is deleted by a bad commit |
| Run | `auto-prune-selfheal` after `argocd app diff` has been read once | `tag` | the repo is the truth, including removals |

Observed in a production tenant: one Application, `targetRevision` on a feature branch, `automated: { prune: false, selfHeal: false }`, `ServerSideApply=true`, no ApplicationSet, no sync waves. That is the Crawl posture serving as production: anyone with push access deploys, drift persists until noticed. Your record names it as the Crawl posture and sets the Walk one; the security record's gate (`argocd-revision-check`) verifies the tag and `selfHeal`.

`ServerSideApply=true` is worth keeping: it avoids the last-applied annotation size limit on large CRDs and makes field ownership explicit.

## Application shape

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: { name: uc-<name>-walk, namespace: argocd }
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/<org>/<iac>.git
    targetRevision: v0.3.0                      # a tag; a branch is a Crawl posture
    path: k8s/overlays/usecases/<name>/stages/walk
  destination: { server: https://kubernetes.default.svc, namespace: uc-<name> }
  syncPolicy:
    automated: { selfHeal: true, prune: false }  # prune: true at Run after a dry run
    syncOptions: [ServerSideApply=true, CreateNamespace=false]
```

`CreateNamespace=false` because the overlay declares `namespace.yaml` with its PSA labels; letting ArgoCD create it loses the labels.

## Private references: what the repo-server needs

When any `resources:` entry is an `ssh://` URL to a private repository (the factory itself when forked, an app repo's `k8s/base`), ArgoCD's repo-server must be able to clone it or the sync fails at refresh with a generic error. Observed, working configuration; list it in `argocd_private_refs`:

- a Secret `argocd-ssh-keys` with the deploy key and an `ssh_config`, mounted in the repo-server at `/app/ssh-keys`
- `GIT_SSH_COMMAND: ssh -F /app/ssh-keys/ssh_config` on the repo-server
- `reposerver.enable.kustomize.helm: "true"` in `argocd-cmd-params-cm` when any component uses `helmCharts`
- `ARGOCD_EXEC_TIMEOUT` / `timeout.reconciliation` at 600 s: a Kustomization with seven SSH refs clones seven repositories per refresh
- a `repository` credential template Secret (`argocd.argoproj.io/secret-type: repo-creds`) for the `ssh://git@github.com/<org>/` prefix

Clone cost is per resource entry: prefer `bundles/*` to several `apps/*` refs in the same namespace.

## Pinning

`remote_refs: pinned-tag` from Walk: every `ssh://...?ref=` is a tag or a commit. A branch ref (`develop`, `main`, `feat/...`) is drift waiting for a push and makes two builds of the same commit differ. Observed: five factory versions (`v1.4.0` ×14, `v1.9.0-rc.1` ×7, `v1.4.1` ×2, `v1.5.1`, plus three branches) in one tenant tree. `remote_refs: mixed` is the honest value when that is the state and the gate (`G-OPS-<n>`, `ci`, `ref-pinning-check`: grep for `?ref=` values that are not tags) is what moves it to `pinned-tag`. Both URL forms occur and both must be pinned: `.git//k8s/...` (double slash, a subdirectory of the factory) and `.git/k8s/base` (single slash, a sibling app repo's root path).

## Distinct environments

Observed: `testing` and `production` write-back targets resolving to the same directory, so a promotion is a no-op and a bad image lands in both. `environments_distinct: true` from Walk means:

1. `stages/walk/kustomization.yaml` exists, builds on its own (`kustomize build k8s/overlays/usecases/<name>/stages/walk`) and differs from the Crawl root (it adds the Walk-tier components and patches).
2. One Application per stage overlay, each with its own `targetRevision`.
3. The image write-back targets one stage's `images:` block; promotion to the next is a second commit (or the tag bump), reviewed.
4. A `ci` gate (`stage-overlay-builds`) builds every `stages/*` and fails if one equals the root.

## What the convention warns about and the tenant does anyway

A global `namespace:` at the root collides with base namespaces; at a sub-overlay level (`namespaces/<ns>/kustomization.yaml`) it is the right tool and the tenant uses it for eleven namespaces. Dead directories not referenced from the root (`namespaces/cert-manager/` in the tenant) are a lint finding; the record's `risks` can name them when reviewing an existing tenant. The tenant's `CLAUDE.md` described a `gitops/{production,testing}/<app>.yaml` tree that did not exist: compare docs with the tree before trusting either.

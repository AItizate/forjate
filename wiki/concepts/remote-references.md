---
title: remote-references
kind: concept
summary: how tenants consume the factory by SSH ref, and where pinning is inconsistent
summary_source: authored
links:
  - concepts/multi-tenant-recursion
---

# Remote references and version pinning

The factory is consumed two ways. Local overlays live in this repo and reference
`../../base` by relative path — always latest, no pinning possible. Remote
tenants live in their own `iac` repos and reference the factory over SSH at a
fixed ref:

```
ssh://git@github.com/{org}/{repo}.git//{path}?ref={git-ref}
```

`?ref=` takes a tag (production), a branch (development) or a commit (debugging).

## The propagation path

A change in `base/` or `components/` reaches a remote tenant only through a
deliberate act on both sides:

1. The change merges here.
2. The factory is tagged: `git tag v1.x.0`.
3. The tenant bumps `?ref=` in its own `kustomization.yaml`.
4. The tenant pushes; ArgoCD clones the factory at the pinned ref and deploys.

Step 3 is the whole point. A remote tenant cannot be broken by a merge into this
repo — only by its own bump. The cost is that a security fix does not propagate
until every tenant chooses to take it, so a factory tag is a release, not a
commit.

## Consumers outside this repo

`im-u/iac` and `globant/iac` consume the factory this way, each pinned to its own
tag. When changing `base/` or a widely-consumed component, the blast radius is
not visible from this repo — it is whatever those repos have pinned. The
`consumed_by` field on a compiled component page covers **local** overlays only,
and says nothing about remote tenants.

## Pinning is inconsistent inside the factory itself

The same discipline the factory asks of its tenants is not uniformly applied to
what it vendors from upstream:

| Component | Vendored ref | Pinned |
|---|---|---|
| [storage-longhorn](../components/storage-longhorn.md) | `v1.9.2` | yes |
| [sealed-secrets](../components/sealed-secrets.md) | `v0.31.0` | yes |
| [monitoring-reloader](../components/monitoring-reloader.md) | `v1.4.14` | yes |
| [continuous-delivery-argocd](../components/continuous-delivery-argocd.md) | `stable` | **no** |

`stable` is a moving branch. Two `kustomize build` runs of the same overlay, on
the same commit, weeks apart, can produce different ArgoCD manifests — which is
precisely the failure mode pinning exists to prevent, in the component whose job
is deploying everything else.

The factory's own guidance says to always pin a remote component to a tag or
commit. Three components follow it; ArgoCD does not.

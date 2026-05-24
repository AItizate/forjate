# `multi-tenant-pattern`

The recursive multi-tenant pattern. See [`docs/overlays/multi-tenant-pattern.md`](../../../docs/overlays/multi-tenant-pattern.md) for the full design.

## Layout

```
multi-tenant-pattern/
  org/                          ← the org overlay (your company defaults)
    kustomization.yaml          ← extends ../../base + org components
  tenants/
    client-a/                   ← per-client overlay, extends ../../org
      kustomization.yaml
      namespace.yaml
    client-b/                   ← same shape, different values
      kustomization.yaml
      namespace.yaml
    (add client-c, client-d, ... as needed)
```

> The org overlay lives in `org/` (not at the root of `multi-tenant-pattern/`) because Kustomize 5.x rejects parent-overlays whose directory contains child overlays in disk — a cycle-detection rule. Putting the org overlay in its own subdirectory side-steps it cleanly.

## Onboarding a new tenant

```bash
cp -r k8s/overlays/multi-tenant-pattern/tenants/client-a \
      k8s/overlays/multi-tenant-pattern/tenants/client-d
# Edit:
#   - tenants/client-d/kustomization.yaml  (secrets refs)
#   - tenants/client-d/namespace.yaml
#   - tenants/client-d/patches/ (subdomain, feature flags, etc.)
kubectl kustomize k8s/overlays/multi-tenant-pattern/tenants/client-d | kubectl apply -f -
```

## ArgoCD auto-discovery

Point an `ApplicationSet` at `tenants/` with a `directory` generator. Each subfolder becomes an Application, automatically.

## Build

```bash
kubectl kustomize k8s/overlays/multi-tenant-pattern/org           # the org overlay alone
kubectl kustomize k8s/overlays/multi-tenant-pattern/tenants/client-a   # client A
```

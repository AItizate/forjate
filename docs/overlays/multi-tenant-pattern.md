# Overlay: `multi-tenant-pattern`

> The same recipe, repeated as many times as you have customers.

## The situation

You have one product. You have N customers. Each customer needs:

- Their own subdomain
- Their own database (or schema, depending on isolation level)
- Their own secrets
- Maybe a different feature flag set
- Strict separation from every other customer's data

You absolutely do **not** want to maintain N copies of the same infrastructure code.

This overlay documents the recursive pattern Forjate is designed around: **base → org overlay → per-client overlay**. The org overlay carries your company's standard shape. The per-client overlay only contains what is different about that client.

## Architecture

![Multi-tenant recursive pattern](../assets/architecture/multi-tenant-pattern.png)

## The recursion

```
k8s/
├── base/                                # Forjate base — never edited per client
│
├── overlays/
│   └── multi-tenant-pattern/
│       ├── README.md
│       ├── org/                         # Your company's standard overlay
│       │   └── kustomization.yaml       # Pulls base + your common components
│       └── tenants/
│           ├── client-a/
│           │   ├── kustomization.yaml   # Pulls ../../org + client A specifics
│           │   ├── namespace.yaml
│           │   ├── patches/             # Subdomain, replicas, feature flags
│           │   └── secrets/             # Sealed secrets for client A only
│           ├── client-b/
│           │   └── ...                  # Same shape, different values
│           └── client-c/
│               └── ...
```

The `org/` overlay is itself a base for `tenants/client-a/`, `tenants/client-b/`, etc. Kustomize handles the chain — there is no special tooling.

> Why `org/` is its own subdirectory and not the root of `multi-tenant-pattern/`: Kustomize 5.x rejects a parent-overlay whose directory contains child overlays on disk (cycle-detection). Putting the org overlay one level deeper side-steps it cleanly while keeping the tree readable.

## `org/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../../base
  - ../../../components/apps/databases/postgres
  - ../../../components/apps/minio/single-server
  - ../../../components/apps/auth/gotrue-auth
  - ../../../components/apps/sealed-secrets
  - ../../../components/apps/monitoring/prometheus
  - ../../../components/apps/continuous-delivery/argocd

labels:
  - pairs:
      app.kubernetes.io/managed-by: kustomize
      org: acme-saas
```

## `tenants/client-a/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../org                              # ← the org overlay
  - ./namespace.yaml

labels:
  - pairs:
      tenant: client-a

# patches:
#   - path: patches/ingress-subdomain.yaml      # client-a.example.com
#   - path: patches/feature-flags-pro-tier.yaml
#   - path: patches/postgres-larger-storage.yaml

# secretGenerator:
#   - name: client-a-secrets
#     envs:
#       - secrets/client-a.env
```

## Notes

- **Identity per tenant** is often the second knob teams reach for. Run **Zitadel** at the org level and give each tenant its own organization/project inside Zitadel — clients log into a shared SSO surface but live in isolated identity scopes. Use GoTrue + OAuth2 Proxy when you don't need full IAM.
- **Namespace per tenant** is the simplest hard isolation. Combine it with NetworkPolicies (in `base/` or as a component) to block cross-namespace traffic.
- **Database isolation** has three flavors, in order of cost: one DB schema per tenant (cheapest, leaks possible), one logical database per tenant on a shared cluster, one full Postgres per tenant. Pick based on compliance — start cheap, graduate when a regulator demands it.
- **Onboarding a new tenant** = `cp -r tenants/client-a tenants/client-d` + edit the 5 patches. CI builds it, ArgoCD deploys it. No new components, no new images.
- **Per-tenant CI/CD** is optional. Most teams point ArgoCD at the `tenants/` directory and let it auto-discover each subfolder as an `Application`.
- This pattern composes with the others: a tenant overlay can itself be `multi-cloud-portable` for that one customer who insisted on AWS, while every other tenant stays on bare metal.

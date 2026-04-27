# Forjate

Kustomize-driven Kubernetes factory for multi-tenant infrastructure. Compose your stack from a shared base, a catalog of reusable components, and tenant-specific overlays.

## Core Philosophy

The architecture is built on three main concepts:

1.  **`k8s/base`**: Contains the foundational, non-optional services required for any tenant to function. This includes core components like ingress controllers (`traefik`), certificate management (`cert-manager`), and storage solutions (`longhorn`). All overlays automatically inherit this base.

2.  **`k8s/components`**: A catalog of optional, reusable applications and services that can be enabled for any tenant. This allows for a clear separation between foundational infrastructure and optional features. The components are organized into logical categories (e.g., `apps/databases`, `apps/brokers`).

3.  **`k8s/overlays/{tenant-name}`**: The specific configuration for a single tenant or environment (e.g., `ai-dev-stack`, `cdc-event-sourcing`). An overlay consumes resources from both `base` and `components` and applies tenant-specific customizations, such as domain names, resource limits, secrets, and configuration maps, primarily through Kustomize patches.

## The Remote Component Pattern

To maximize flexibility and empower Subject Matter Experts (SMEs), this factory supports a "remote component" pattern.

Instead of defining all components locally, a component in the `k8s/components` catalog can simply be a `kustomization.yaml` file that points to an external Git repository.

**Example: `k8s/components/apps/static-site/kustomization.yaml`**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - https://github.com/some-sme/static-site-component/k8s/base?ref=main
```

This approach allows:
-   **Decentralized Ownership**: SMEs can manage the lifecycle, CI/CD, and manifests of their own components in dedicated repositories.
-   **Centralized Composition**: This factory remains the single source of truth for *composing* the final infrastructure for each tenant, without needing to manage the implementation details of every component.

## How to Manage Tenants

-   **Adding a Feature**: To enable a feature for a tenant, add a reference to its path from `k8s/components` into the `resources` section of the tenant's `kustomization.yaml` file (e.g., `k8s/overlays/ai-dev-stack/kustomization.yaml`).
-   **Customization**: Apply tenant-specific configurations using patches, config maps, and secrets within the tenant's overlay directory.

For instructions on how to add new components to the catalog, see `CONTRIBUTING.md`.

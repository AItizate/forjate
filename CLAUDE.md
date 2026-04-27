## Overview

This is **Forjate**, a Kustomize-driven monorepo for managing multi-tenant / multi-environment Kubernetes infrastructure. It follows a Base + Overlays + Components pattern to enable DRY, scalable infrastructure as code.

The factory supports two consumption patterns: **local overlays** (tenants inside this monorepo) and **remote references** (independent tenant repos that pull base/components via SSH git URLs).

## Project Structure

```
k8s/
├── base/                 # Foundation: core services (traefik, cert-manager, longhorn, minio)
│   ├── apps/            # Base app deployments, services, ingresses (non-tenant-specific)
│   ├── namespaces/      # Kubernetes namespaces
│   └── kustomization.yaml
├── components/          # Reusable optional components organized by category
│   └── apps/
│       ├── databases/
│       ├── brokers/
│       ├── ai-models/
│       ├── monitoring/
│       └── ... (other categories)
└── overlays/           # Tenant-specific customizations (patrón local)
    ├── ai-dev-stack/
    ├── cdc-event-sourcing/
    └── agentic-orchestration/

docs/                   # Comprehensive architecture and app documentation
scripts/               # Automation tools (if present)
```

## Architecture Model

The system works on three key concepts:

1. **`k8s/base`**: Environment-agnostic foundation. Every tenant inherits this. Contains core services needed by all tenants (Traefik, cert-manager, Longhorn storage, MinIO).

2. **`k8s/components`**: Optional, reusable components organized by category (e.g., `ai-models/ollama`, `databases/postgres`). Components can be **local** (manifests in this repo) or **remote** (Git URL references to external repos managed by SMEs).

3. **`k8s/overlays/{tenant}`**: Tenant-specific configuration. Each overlay:
   - Includes the base (via `../../base` reference)
   - Includes optional components from `k8s/components`
   - Applies customizations via **patches**, **configMapGenerator**, and **secretGenerator**
   - Contains:
     - `kustomization.yaml`: defines resources, patches, configmaps, secrets
     - `configs/`: files for ConfigMaps (e.g., litellm-config.yaml)
     - `secrets/`: `.env` files for Kubernetes Secrets
     - `patches/`: YAML snippets that modify base resources (ingress hostnames, image tags, replicas, etc.)
     - `namespaces/`: optional namespace-scoped sub-overlays

## Multi-Tenant Architecture: Local vs Remote Patterns

The factory serves tenants in two ways:

### Patrón LOCAL (overlays internos)

Tenants that live inside this monorepo as overlays under `k8s/overlays/`. They reference base via relative paths.

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/databases/postgres
```

**Example overlays:** `ai-dev-stack`, `cdc-event-sourcing`, `agentic-orchestration`

**Use when:** the tenant only needs k8s infra, is a dev/personal environment, or doesn't need its own CI/CD workflows.

### Patrón REMOTO (repos IAC independientes)

Tenants with their own `iac` repos that reference this factory's `base/` and `components/` remotely via SSH git URLs.

```yaml
# my-org/iac/k8s/kustomization.yaml
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=v1.0.0
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/sealed-secrets?ref=v1.0.0
  - cloudflare-issuer.yaml       # archivos locales del repo
  - ./namespaces/default          # overlays locales del repo
```

**Use when:** the tenant is a full organization with its own app repos, CI/CD pipelines, and gitops workflows.

### SSH Remote Reference Syntax

```
ssh://git@github.com/{org}/{repo}.git//{path-inside-repo}?ref={git-ref}
```

`?ref=` accepts: tags (`v1.0.0`, recommended for prod), branches (`main`, for dev), or commits (`abc1234`, for debugging).

**Requirements for remote pattern:**
1. Access to `AItizate/forjate` (public repo, or SSH key for private forks)
2. In GitHub Actions: deploy key or SSH key as secret (if using a private fork)
3. In ArgoCD: credentials configured for cloning

### Comparison

| Patrón | Referencia a base | Versionado | CI/CD propio |
|--------|-------------------|------------|--------------|
| **Local** | `../../base` (relativo) | Siempre latest | No — usa webhook de la factory |
| **Remoto** | `ssh://...?ref=v1.0.0` | Pinned a tag | Sí — workflows propios en `.github/` |

### Update Flow (remote pattern)

1. Change lands in `base/` or `components/` in this factory
2. Tag the factory: `git tag v1.x.0`
3. Consumer repo updates `?ref=v1.0.0` → `?ref=v1.x.0` in its `kustomization.yaml`
4. Consumer pushes → ArgoCD detects change → clones factory at pinned ref → deploys

### Creating a New Remote Tenant

1. Create a new iac repo for your tenant
2. SSH refs in `kustomization.yaml` point to this factory
3. Adapt: domains, namespaces, patches, secrets, gitops manifests
4. Create deploy key / SSH key for factory access from CI/CD and ArgoCD
5. Tag the factory if a stable version is needed: `git tag v1.x.0`

## Kustomize Workflow

When you run `kustomize build k8s/overlays/ai-dev-stack`:

1. Loads overlay's `kustomization.yaml`
2. Includes base resources from `k8s/base`
3. Includes enabled components from `k8s/components`
4. Applies patches (highest priority)
5. Generates ConfigMaps and Secrets from files
6. Outputs final Kubernetes manifest

Patches and generators take precedence, so tenant customizations always override base defaults.

## Common Tasks

### Validating Kustomize Output

Check the manifest that would be applied to a tenant:

```bash
kustomize build k8s/overlays/ai-dev-stack > output.yaml
```

### Enabling a Component for a Tenant

Edit the tenant's `k8s/overlays/{tenant}/kustomization.yaml` and add to `resources`:

```yaml
resources:
  - ../../base
  - ../../components/apps/databases/postgres  # Add new component
```

### Customizing for a Tenant

**Option 1: Add a patch** (for modifying existing resources)
- Create YAML file in `k8s/overlays/{tenant}/patches/`
- Add to `patches` section in `kustomization.yaml` with target specification

**Option 2: Add a ConfigMap** (for application config)
- Create YAML file in `k8s/overlays/{tenant}/configs/`
- Add `configMapGenerator` entry in `kustomization.yaml`

**Option 3: Add a Secret** (for sensitive values)
- Create `.env` file in `k8s/overlays/{tenant}/secrets/`
- Add `secretGenerator` entry in `kustomization.yaml`

### Adding a Local Component

1. Create directory: `k8s/components/apps/{category}/{component-name}`
2. Add Kubernetes manifest files (deployment.yaml, service.yaml, etc.)
3. Create `kustomization.yaml` listing the manifest files
4. Reference in tenant overlays: `- ../../components/apps/{category}/{component-name}`

Use placeholder values (e.g., `my-app.example.com` for hostnames) that tenants can patch.

### Adding a Remote Component

1. Create stub directory: `k8s/components/apps/{category}/{component-name}`
2. Create `kustomization.yaml` with Git URL:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization
   resources:
     - https://github.com/owner/repo/k8s/base?ref=v1.2.0
   ```
3. **Always pin to a specific tag or commit hash** (`?ref=...`) for stability
4. Reference in tenant overlays like a local component

## Key Applications (in k8s/base)

- **Traefik**: Ingress controller and reverse proxy
- **cert-manager**: TLS certificate management (Let's Encrypt integration)
- **Longhorn**: Block storage provisioner
- **MinIO**: S3-compatible object storage
- Namespace definitions for: cert-manager, security, shared, traefik, ai-tools

See `docs/apps/` for detailed documentation on each application.

## Contributing Guidelines

See `CONTRIBUTING.md` for detailed patterns on:
- Adding local components
- Adding remote components
- Enabling components in tenant overlays

Key principle: Keep `base` generic and environment-agnostic. Use overlays for all customization.

## Documentation

Refer to these documents for deep dives:

- `docs/architecture-overview.md`: Detailed architecture explanation with flow diagrams
- `docs/service-integration.md`: How services interact and flow diagrams
- `docs/apps/`: Individual app documentation (traefik, cert-manager, longhorn, etc.)
- `docs/tenant-onboarding/`: Guides for configuring specific services (oauth2-proxy, litellm, open-webui, storage)
- `CONTRIBUTING.md`: How to add new components

## Useful Patterns

- **Placeholder hostnames in base**: Use `service-name.example.com` in base Ingresses. Tenants patch with real domains.
- **Replica count patches**: Common customization for resource-constrained environments (e.g., set replicas=1 for dev, replicas=3 for prod).
- **Namespace-scoped configs**: Use namespace sub-overlays for fine-grained per-namespace customizations without duplicating base resources.
- **Remote components for decentralization**: Let SMEs manage their own components in external repos. This factory composes them.

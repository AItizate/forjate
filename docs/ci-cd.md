# CI/CD ecosystem for Forjate consumers

Forjate doesn't ship its own CI/CD framework. It plugs into the **AItizate org's existing CI/CD building blocks** so a tenant repo can be productive in minutes without inventing its own pipeline.

This page is the map. If you are adopting Forjate from a new tenant repo, read it once.

## The pieces

```
┌──────────────────────────────┐       ┌──────────────────────────────┐
│  AItizate/gh-actions-templates│       │  YOUR APP REPO               │
│                              │       │                              │
│  Reusable build / push /     │◄──────┤  .github/workflows/ci.yml    │
│  deploy workflows (called    │  uses │  (just calls the templates)  │
│  from any consumer repo)     │       │                              │
└──────────────────────────────┘       └──────────────┬───────────────┘
                                                      │ on push to main
                                                      │ build + push image
                                                      │ then dispatch event
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │  AItizate/forjate (this repo)│
                                       │                              │
                                       │  .github/workflows/          │
                                       │  sync-app-image.yml          │
                                       │  (receives the event,        │
                                       │   updates IaC tag, opens PR) │
                                       └──────────────┬───────────────┘
                                                      │
                                                      │ ArgoCD pulls
                                                      ▼
                                                 your cluster
```

## Reusable workflows you can call

All live in [`AItizate/gh-actions-templates`](https://github.com/AItizate/gh-actions-templates). Call them like this from your repo:

```yaml
jobs:
  build:
    permissions:
      contents: read
      id-token: write   # for AWS OIDC, if you use the ECR template
    uses: AItizate/gh-actions-templates/.github/workflows/<template-name>.yml@main
    with:
      # ... inputs ...
    secrets:
      # ... secrets ...
```

| Template | Purpose | When to use |
|----------|---------|-------------|
| `build-push-generic-template.yml` | Build a Docker image, push to any registry (Docker Hub, GHCR, etc.) | Most overlays — works with the GHCR-by-default convention in Forjate |
| `build-push-ecr-template.yml` | Build, push to AWS ECR via OIDC | When your tenant runs on EKS or you want IAM-less image push |
| `build-push-template.yml` | Build + push to ECR (legacy) | Prefer the generic or ECR templates above |
| `deploy-template.yml` | `kubectl apply` against an EKS cluster | Use only if you are NOT on GitOps. Forjate prefers ArgoCD via the `sync-app-image` flow below |

## The GitOps loop (how an image lands in the cluster)

Forjate uses the **GitHub-event-driven GitOps pattern**:

1. Your app repo's CI builds and pushes a new image (e.g. via `build-push-generic-template`).
2. The last step in that CI **fires a `repository_dispatch` event** to this repo (`AItizate/forjate`), with the new image tag.
3. [`forjate/.github/workflows/sync-app-image.yml`](../.github/workflows/sync-app-image.yml) catches the event, opens a PR that bumps the image tag in the relevant overlay's `kustomization.yaml`.
4. You (or a merge automation) merge the PR.
5. ArgoCD detects the commit and rolls the new tag out.

**Why this pattern over CI-direct-deploy?**
- The cluster is never written to by CI. Only ArgoCD reconciles. Less blast radius.
- The IaC repo is the audit log of every deployment.
- Rollback = revert a commit in the IaC repo.

### Dispatch payload contract

When your CI calls back into this repo, the `repository_dispatch` payload must look like:

```json
{
  "event_type": "app-image-updated",
  "client_payload": {
    "app_name": "your-app-name",
    "new_tag": "sha256:abc123..."
  }
}
```

The `sync-app-image.yml` workflow locates the matching overlay by `app_name` and replaces the tag.

## Local quality gates (forjate internal)

This repo also runs its own validation on every PR:

| Workflow | Triggers on | Purpose |
|----------|-------------|---------|
| [`validate-kustomize.yml`](../.github/workflows/validate-kustomize.yml) | Changes under `k8s/**` | Builds every overlay + component with `kustomize build`, validates each manifest with `kubeconform` against upstream + CRD schemas |
| [`sync-app-image.yml`](../.github/workflows/sync-app-image.yml) | `repository_dispatch: app-image-updated` | The GitOps loop endpoint (see above) |

Consumer tenants don't need to install these — they're for keeping Forjate itself honest.

## What's NOT here yet

Things on the roadmap but not implemented (see open issues):

- A reusable `validate-kustomize` workflow in `gh-actions-templates` (so tenants can run the same gate on their own overlay repos without duplicating yaml).
- A `scan-image` template (Trivy + Cosign sign).
- A `release-tag` template (auto-tag on version bump, à la `scitrix-tech/iac`).

## Cheat sheet for a new tenant repo

```yaml
# .github/workflows/build.yml in your app repo
name: build
on:
  push:
    branches: [main]
jobs:
  build:
    uses: AItizate/gh-actions-templates/.github/workflows/build-push-generic-template.yml@main
    with:
      repository_name: your-app
      image_tag: ${{ github.sha }}
      registry: ghcr.io
    secrets:
      registry_username: ${{ secrets.GHCR_USER }}
      registry_password: ${{ secrets.GHCR_TOKEN }}

  notify-forjate:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch tag update
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.FORJATE_DISPATCH_TOKEN }}
          repository: AItizate/forjate
          event-type: app-image-updated
          client-payload: |
            {
              "app_name": "your-app",
              "new_tag": "${{ github.sha }}"
            }
```

Two files, ten minutes, and your tenant is plugged into the Forjate GitOps loop.

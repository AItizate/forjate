# Shared CI templates

`AItizate/gh-actions-templates` is part of the Forjate ecosystem the way the factory is: a dependency every tenant pins, not a catalog choice. A use case does not write its own build, scan and push pipeline; it calls a template. Writing one by hand is drift with a commit message, the same way a hand-rolled factory component is. Pin to a **major tag** (`@v1`); `@main` is a branch ref and your `remote_refs` rule applies to it too.

Templates (observed 2026-10-07, `v1.1.0`):

| Template | Does | Stage it enters | Inputs that matter |
|----------|------|-----------------|--------------------|
| `pr-validation-template.yml` | Conventional-commit check on PRs | Crawl, on the use case's own repo | `require_conventional_commits` |
| `build-push-generic-template.yml` | Build, **Trivy scan**, push to any registry | Walk | `registry_url`, `repository_name`, `image_tag` (the SHA), `docker_file`, `trivy_severity`, `push_image` |
| `build-push-ecr-template.yml`, `build-push-template.yml` | Same for AWS ECR | Walk, only when the registry is ECR | `ecr_repository`/`repository_name`, `aws_region` |
| `release-tag-template.yml` | Creates the release tag | Walk | `version`, `prerelease`, `target_commitish` |
| `deploy-template.yml` | Deploys to EKS | Run, only on EKS; GitOps tenants do not call it, ArgoCD reconciles | `docker_image`, `aws_region` |
| `webhook-notification-template.yml` | Notifies a webhook of the run's result | Walk | `repository`, `ref`, `run_id`, `message` |

What this means for your record:

- `image_build: gh-actions-templates/build-push-generic@v1` from Walk (or the ECR variant when the registry is ECR). The Trivy scan the template runs **is** the image-scan gate; do not ask the quality or security expert for a second scanner, point the gate's `check.ref` at the template's job.
- `image_writeback` stays `repository_dispatch+yq`: the template pushes the image, the consumer repo dispatches `update-image-tag`, the tenant's workflow writes the SHA into `images:`. `docs/ci-write-back-integration.md` has the wiring.
- `ci_templates_ref: v1` in `settings`, and a risk when a tenant's workflow calls `@main`.
- The scaffolded workload (`forjate:app-scaffold`) ships `.github/workflows/` files that `uses:` these templates; a generated pipeline that reimplements build and push is a defect.

Full documentation and the lifecycle diagrams (CI pipeline, GitOps loop, DevSecOps gates): the repo's README and `docs/ci-cd.md` in the factory.

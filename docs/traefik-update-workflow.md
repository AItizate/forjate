## Brief overview
This document outlines the preferred workflow for updating Kubernetes applications that are managed as plain manifests but were originally generated from a Helm chart. The goal is to ensure updates are consistent, safe, and reproducible.

## Helm-based Manifest Updates
- **Avoid Manual Edits:** When a new version of an application is available, do not simply update the image tag in the `Deployment` or `StatefulSet` manifest. This can lead to inconsistencies if the new version's Helm chart includes other changes (e.g., new arguments, RBAC permissions, or configuration options).
- **Regenerate from Source:** The correct procedure is to regenerate the manifests using the `helm template` command with the new chart version.
- **Preserve Configuration:** When regenerating, ensure that any existing custom configurations (originally set via `--set` flags or a `values.yaml` file) are preserved in the new `helm template` command. This can be done by inspecting the existing manifests for custom arguments or settings.
- **Replace, Don't Patch:** Overwrite the old manifest files entirely with the newly generated ones to ensure a clean update.

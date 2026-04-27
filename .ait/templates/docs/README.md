# Welcome to {{ TENANT_NAME }}'s Infrastructure

This repository contains all the Infrastructure as Code (IaC) for the **{{ TENANT_NAME }}** project. It is managed using Kubernetes and Kustomize.

## Overview

-   **Domain:** `{{ TENANT_DOMAIN }}`
-   **Environment:** The primary environment is `production`.

## How to Deploy

The infrastructure is managed declaratively. To deploy or update the environment, apply the `production` overlay using Kustomize.

### Prerequisites

-   `kubectl` connected to your target Kubernetes cluster.
-   `kustomize` installed.

### Deployment Command

From the root of this repository, run:

```bash
kustomize build k8s/overlays/production | kubectl apply -f -
```

This command builds the final Kubernetes manifests by combining the `base` configurations with the `production` overlay and applies them to your cluster.

## Enabled Features

The following services have been enabled for this tenant:

{{ FEATURES_LIST }}

To find the specific hostnames for each service, please inspect the `ingress.yaml` files within each application's directory under `k8s/base/apps/`. The hostnames are typically patched in the production overlay.

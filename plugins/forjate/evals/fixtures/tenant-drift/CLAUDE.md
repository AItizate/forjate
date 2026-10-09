# CLAUDE.md — acme/iac

## Purpose

GitOps manifests for the acme tenant of the Forjate factory.

## Structure

```
.github/workflows/
  gitops-webhook.yml                # Receive dispatch, update gitops files, push

gitops/
  production/
    website.yaml                    # image tag for production website
  testing/
    website.yaml                    # image tag for testing website
```

## Adding a new app

1. Add a case to `gitops-webhook.yml` under the `APP_NAME` switch
2. Add initial `gitops/{production,testing}/<app>.yaml` files

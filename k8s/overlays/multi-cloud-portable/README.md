# `multi-cloud-portable`

Reference overlay — **bare-metal flavor**. See [`docs/overlays/multi-cloud-portable.md`](../../../docs/overlays/multi-cloud-portable.md) for the cross-provider design.

This directory deliberately only contains the bare-metal flavor. The AWS / GCP / Azure flavors are sibling directories you create when you need them:

```
k8s/overlays/
  multi-cloud-portable/         ← this one (bare metal)
  multi-cloud-portable-aws/     ← future
  multi-cloud-portable-gcp/     ← future
  multi-cloud-portable-azure/   ← future
```

Each flavor pulls in `components/apps/iac/crossplane` plus the relevant provider package and patches the StorageClass + DB connection secret source.

## Build & deploy

```bash
kustomize build k8s/overlays/multi-cloud-portable | kubectl apply -f -
```

## Provisioning the `app-database` and `app-object-store` secrets

In the bare-metal flavor, these point to the in-cluster Postgres and MinIO Services. Provide them via `sealed-secrets` or any other secret manager you prefer.

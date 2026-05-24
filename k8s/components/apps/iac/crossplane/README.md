# Crossplane

> Declare cloud resources as YAML, next to your workloads.

Crossplane turns any Kubernetes cluster into a control plane for the world outside it: AWS, GCP, Azure, Cloudflare, GitHub, Postgres servers, you name it. From Forjate's perspective, Crossplane is the hinge that makes the "anywhere" promise concrete — when an overlay needs a managed bucket, a CloudSQL instance, or a Cloudflare DNS record, the overlay asks for it in the same Kustomize file that asks for an Ingress.

## What this component installs

- The Crossplane core (CRDs + controller) via the upstream Helm chart, pinned to a stable version
- The `crossplane-system` namespace
- No providers by default — overlays opt in to the providers they need

## Why it lives in Forjate

The base is hardware-agnostic. Components are the optional building blocks. Crossplane belongs in **`iac/`** because it is not an app you run for users — it is the way an overlay describes the cloud resources it depends on, declaratively, in the same place as everything else.

This keeps the contract intact:

```
overlay/kustomization.yaml
  ├── ../../base                                    # what every tenant needs
  ├── ../../components/apps/iac/crossplane          # control plane for cloud resources
  ├── ../../components/apps/databases/postgres      # in-cluster DB (free)
  └── ./cloud-resources/aws-s3.yaml                 # OR a Crossplane-managed S3 bucket
```

## Enabling a provider in your overlay

Crossplane providers are installed as additional CRDs after the core is up. The pattern in an overlay:

```yaml
# overlay/cloud-providers/aws.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.x.x
```

Then reference it from the overlay's `kustomization.yaml` and supply credentials via a Secret (use `external-secrets` or `sealed-secrets` from the components catalog).

## Examples

See `examples/` for working snippets:

- `aws-s3-bucket.yaml` — a managed S3 bucket
- `gcp-cloudsql-postgres.yaml` — a managed Postgres on GCP
- `azure-storage-account.yaml` — a managed Azure Storage Account

These are reference shapes, not turnkey overlays. Adapt them to your provider config and IAM bindings.

## When NOT to use Crossplane

If the entire tenant runs on bare metal or a single VPS and never reaches into a cloud provider, skip Crossplane. The base + in-cluster components (Postgres, MinIO, Longhorn, MetalLB) already cover storage, databases, ingress and load balancing without any cloud account.

Add Crossplane the day an overlay needs a managed service that lives outside the cluster — and only the providers it actually uses.

## Further reading

- [Crossplane docs](https://docs.crossplane.io/)
- [Upbound provider marketplace](https://marketplace.upbound.io/providers)

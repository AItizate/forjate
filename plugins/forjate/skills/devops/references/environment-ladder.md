# Environment ladder

| | Crawl | Walk | Run |
|---|---|---|---|
| `environment` | `ephemeral-k3d` | `shared-cluster` | `prod-cluster` |
| `cluster_shape` | `k3d-1-node` on a laptop or a CI runner | `k3s-3-node` (or RKE2), embedded etcd | `k3s-ha-3+` plus managed services where the architecture asks |
| `storage_class` | `local-path` (k3d default; Longhorn does not run on k3d) | `longhorn`, 3 replicas | `longhorn` plus operator-managed databases |
| `deploy_method` | `ephemeral.sh up <name>` | `argocd` | `argocd` |
| isolation | `uc-<name>` namespace on the shared k3d cluster, or a dedicated cluster when the overlay installs CRDs, operators or StorageClasses | namespace per use case, NetworkPolicy isolation | namespace per use case, quotas, PSA restricted |
| what proves it | the verify Job exits 0 | the same Job as a canary plus metrics | SLOs, restore and rollback rehearsed |
| typical cost | 0 to 5 USD/month | 60 to 150 USD/month (3 small nodes) | 200 to 500 USD/month plus managed services |

Source: `docs/lab-to-production.md` and `scripts/ephemeral/README.md`. The stage planner sets the tier; you place it on hardware.

## What the ephemeral runner gives you at Crawl

`ephemeral.sh up` does preflight, creates or reuses the k3d cluster, seeds `.env` files from their examples, applies the overlay, stamps the TTL, runs seed, run and verify in order and prints the endpoints from `usecase.yaml`. There is nothing for you to add at Crawl except sizing: `patches/<component>-resources.yaml` so the components fit a laptop, and `spec.isolation: dedicated` when something cluster-scoped is installed. Observability is the Job logs the runner prints; rollback is `down` and `up`.

## Cost shapes

Write the shape in `rationale` and the number in `estimated_cost_usd_month`:

- Crawl: `0` on a laptop; `5` for a small VPS running k3d in CI.
- Walk: `3 × 4 vCPU / 8 GB nodes (Hetzner CPX21-class) ≈ 60 to 90`; add `30 to 60` for a 200 GB offsite dump target; a GPU node for Walk inference latency is `150 to 300` more and usually the open question.
- Run: Walk plus managed Postgres or object storage within residency (`50 to 200`), Velero offsite target (`20 to 50`), observability retention (`20 to 50`).

The number stays inside the business record's envelope for the stage. When it cannot, the record says what the envelope buys instead (no GPU, single Longhorn replica, no offsite) and the business expert changes `go_no_go`, not you.

## Node placement

Mixed architectures (a Pi next to an x86 node) and old CPUs (no AVX for MongoDB 7) are real in the tenants this factory serves. When the brief or the cluster shape implies it, the record names a `nodeSelector` label convention (`<tenant>/cpu-arch`) and the image downgrades it forces, each with the reason; the kustomize skill writes the patches.

# Stage defaults

Condensed from `docs/lab-to-production.md` and `docs/overlays/CONVENTION.md`. Figures are the factory's reference numbers; a pack or the business expert may override them.

| | Crawl | Walk | Run |
|---|---|---|---|
| **Forjate tier** | `lab` | `mvp` | `production` |
| **Proves** | the automation works end to end on real-shaped data, one user | real users can rely on it, internally, on one cluster | SLAs, audits, multi-tenancy |
| **Where it runs** | k3d via `scripts/ephemeral/ephemeral.sh`, or a single-node k3s | 3-node k3s/RKE2 with Longhorn + MetalLB | 3+ nodes plus managed services and offsite backup |
| **Reference overlay** | `quickstart`, `usecases/*` | `bare-metal-starter` | `multi-tenant-pattern`, `multi-cloud-portable` |
| **Platform defaults** | placeholder secrets via `.env.example`, no auth, PSA `privileged` | Sealed Secrets, ArgoCD, GoTrue + oauth2-proxy, Prometheus + Grafana, Cloudflare Tunnel, NetworkPolicy default-deny, PSA `baseline` | External Secrets / Vault, Velero, PSA `restricted`, OTel pipeline, DB operators, image signing |
| **Typical cost USD/month** | 0 to 5 | 60 to 150 | 200 to 500 plus managed services |
| **Typical duration** | days | weeks | ongoing |

## Typical exit criteria

**Crawl → Walk**

- `G-Q-1` verify Job of the use case exits 0 on the seeded dataset (`verify-job`)
- `G-BIZ-1` the success metric from the brief was measured once on the PoC and the approver saw the number (`manual`, approver)
- `G-DS-1` retention of PoC data decided (`manual`)

**Walk → Run**

- `G-Q-2` success metric meets the brief's target over a defined window (`metric`)
- `G-SEC-1` namespace is default-deny with documented egress allow-list (`ci`)
- `G-OPS-1` rollback rehearsed once from git (`manual`, operator)
- `G-OPS-2` dashboards and alerts for the use case's golden signals exist (`manual`)

**Run (steady state)**

- `G-SEC-2` PSA `restricted` enforced on the namespace (`ci`)
- `G-SEC-3` no plaintext secret in git; mechanism per pack (`ci`)
- `G-COMP-1` compliance record signed; data residency and egress documented (`manual`, compliance)
- `G-OPS-3` backup restore rehearsed (`manual`)

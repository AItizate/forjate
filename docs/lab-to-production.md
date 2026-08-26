# Lab → MVP → Production

Forjate today is **Lab-grade**. That's a deliberate starting point, not a limitation.

This page explains what changes as you climb from Lab to MVP to Production, what gets added at each step, what gets replaced, and roughly what each stage costs to run. The TL;DR: **you don't pay for production-grade features until you need them**, and the upgrade is mostly additive — not a rewrite.

![Lab to Production](./assets/architecture/lab-to-production.png)

## The three stages

### 🧪 Lab — what you get today

| | |
|---|---|
| **Hardware** | 1 Raspberry Pi 5, a mini-PC, an old laptop, or a single small VPS |
| **Cost** | USD 0 (your own hardware) to ~USD 5/mo (a $5 VPS) |
| **Cluster** | k3s, single node, SQLite backend |
| **Storage** | Longhorn single-replica, MinIO single-server |
| **Network** | Traefik + cert-manager, no MetalLB needed (single node) |
| **Auth** | GoTrue + OAuth2 Proxy (or none if local) |
| **GitOps** | Optional — `kubectl apply -k` works fine here |
| **Security** | Default Kubernetes (`privileged` admission, no NetworkPolicies) |
| **Backup** | None |
| **Use case** | Learning (see [the learning path](./learning-path.md)), weekend projects, MVP demos, the `home-edge-lab` overlay |

This is where most of the `docs/overlays/` library lives today. Everything is shippable, but you're trusting the platform to not turn against you. **Don't put paying customers here.**

### 🏗️ MVP — production-shaped, single-cluster

What you add or change when you have real users:

| Change | Why | Tracked in |
|--------|-----|------------|
| 3-node cluster on bare metal or 3 small VPS | No single point of failure | — |
| k3s HA with embedded etcd (or RKE2) | SQLite doesn't scale past 1 node safely | — |
| Longhorn with 3 replicas, MetalLB for LoadBalancers | Storage and ingress without a cloud account | — |
| **ArgoCD + Sealed Secrets** | Git becomes the source of truth, you stop running `kubectl apply` from your laptop | [`bare-metal-starter`](overlays/bare-metal-starter.md) |
| **Prometheus + Grafana + Cloudflare Tunnel** | You can see what's happening, and the only public ingress is one outbound tunnel (no open ports) | [`bare-metal-starter`](overlays/bare-metal-starter.md) |
| **NetworkPolicies default-deny in base/** | A pod can't reach anything it wasn't explicitly allowed to | [#4](https://github.com/AItizate/forjate/issues/4) |
| **Pod Security Admission set to `baseline`** | No more privileged pods by default (PSA `restricted` lands at Production) | [#5](https://github.com/AItizate/forjate/issues/5) |
| **Helm chart versions pinned everywhere** | Upstream chart updates don't surprise you mid-week | [#7](https://github.com/AItizate/forjate/issues/7) |

| | |
|---|---|
| **Hardware** | 3 small servers (Hetzner CPX21, refurbished mini-PCs, or 3× VPS) |
| **Cost** | ~USD 60–150/mo total infra |
| **Use case** | Real users, ~10K MAU, internal tools, an early SaaS, a B2B agentic product |

The big jump from Lab to MVP is **trust**. Everything you do now goes through git and policy gates. You can sleep without nightmares of `kubectl delete ns prod`.

### 🏛️ Production — multi-tenant or compliance-graded

What you add when "real" means SLAs, audits, or multi-tenancy:

| Change | Why | Tracked in |
|--------|-----|------------|
| **Velero with offsite backup destination** | Cluster-level DR. Restore a namespace in minutes, not days | [#6](https://github.com/AItizate/forjate/issues/6) |
| **Pod Security Admission tightened to `restricted`** | Block all the foot-guns. The reference deployments in this PR are already compatible | [#5](https://github.com/AItizate/forjate/issues/5) |
| **Postgres via operator (CloudNativePG / Zalando / PGO)** | HA postgres with failover and PITR, not single-statefulset | _(future issue)_ |
| **Image scanning + Cosign signing in CI** | You stop deploying images you can't trace to source | _(future issue)_ |
| **OpenTelemetry full pipeline (LGTM / Datadog / cloud)** | Metrics + logs + traces, not just metrics | _(future issue)_ |
| **Crossplane + external managed services (per [`multi-cloud-portable`](overlays/multi-cloud-portable.md))** | Specific workloads bursting to cloud where it makes sense | already documented |
| **`multi-tenant-pattern` for client isolation** | Hard isolation per customer via namespace + NetworkPolicy + RBAC | already documented |

| | |
|---|---|
| **Hardware** | 3+ nodes on-prem **plus** a managed service or two for state, plus an offsite backup target |
| **Cost** | USD 200–500/mo for most teams; scales with the managed services you opt in to |
| **Use case** | Paying customers, regulated industries, multi-tenant SaaS |

## How to read this

Three things matter about this trajectory:

1. **It's additive, not destructive.** You don't rewrite your overlays to go from Lab to Production. You add components (`apps/backup/velero`), tighten labels (`pod-security.kubernetes.io/enforce: restricted`), pin versions. The base + components don't change.
2. **Each stage is independently useful.** The home lab on a Pi is a Lab forever — and that's fine. The MVP three-node cluster is real production for the long tail of B2B SaaS. Production is when you're chasing five-nines or auditors.
3. **Cost grows with capability, not with the platform.** Forjate doesn't charge per node, per tenant, or per request. What grows is the hardware you choose and the managed services you opt into.

## Status today

This PR (the one introducing this document) brought Forjate to **Lab-grade with production-shaped reference deployments**. The deployments already carry the security context, resource shape, and probes that Production demands — they just don't have the platform-level gates around them yet.

Each gate (NetworkPolicies, PSA, Velero, Helm pinning) has its own GitHub issue:

- 🔐 [#4 — NetworkPolicies default-deny](https://github.com/AItizate/forjate/issues/4)
- 🛡️ [#5 — Pod Security Admission labels](https://github.com/AItizate/forjate/issues/5)
- 💾 [#6 — Velero backup component](https://github.com/AItizate/forjate/issues/6)
- 📌 [#7 — Helm chart version pinning audit](https://github.com/AItizate/forjate/issues/7)

Pick the stage you need, install accordingly, and grow the rest on your own pace.

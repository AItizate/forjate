# Forjate

Your infra shouldn't be the thing stopping you from creating.

## Why

I went through hand-copied YAMLs. I went through Helm nightmares —
too many values, too many tenants, too many unknowns.
Every change was a leap of faith.

Forjate was born from that. From wanting to actually learn
infrastructure, and from needing to ship things fast without
the YAML winning.

It's opinionated. The tool selection reflects what I use,
what taught me something, and what let me create. This isn't
a neutral framework trying to please everyone — it's a toolbox
that works.

With this I spun up a dev tenant in under 15 minutes.
And a full company — website, DNS, backend, frontend, BFF,
data pipeline, AI tools — in one week.
With vibe coding, of course.

## What it is

A Kustomize-driven Kubernetes infrastructure factory.
Three concepts:

- **Base** — the services every tenant needs (Traefik, cert-manager, Longhorn, MinIO)
- **Components** — a catalog of 40+ optional pieces you activate per tenant
- **Overlays** — your environment's specific config. Patches, secrets, configs. No duplication.

```
k8s/
├── base/          # Foundation. Everyone inherits this.
├── components/    # Catalog. Pick what you need.
└── overlays/      # Your environment. Customize without breaking.
```

## Built for real hardware

The idea is simple: low-cost hardware should be enough to create
serious things.

My first cluster ran on Raspberry Pis, a 2009 Compaq Presario,
and a 2015 MacBook Pro Retina. That's why Forjate starts with
k3s — the smallest Kubernetes that still does everything.

Complex ZTNA applications can run on a few servers. You control
your data. You own your infrastructure. You scale what's private
on your terms.

This also means Forjate can live as parallel infrastructure
inside an existing organization — a tech lab that grows alongside
production, or community-maintained plugins that adapt to
a reality of low cost and sustainability.

Not everyone starts with a cloud budget.
Some of us start with what's in the drawer.

## Component catalog

| Category | Components |
|----------|------------|
| AI & ML | Ollama, vLLM, LanceDB, Milvus, Docling |
| Databases | PostgreSQL, MariaDB, MongoDB, Redis, etcd |
| Brokers | RabbitMQ, NATS, Mosquitto |
| CDC | Debezium (Postgres/Mongo/MariaDB → RabbitMQ/NATS) |
| Monitoring | Prometheus, Grafana, OTEL Collector, Reloader |
| Workflows | Temporal |
| Auth & Security | GoTrue, OAuth2 Proxy, Vault, External Secrets, Sealed Secrets |
| Productivity | Affine, AppFlowy, Formbricks |
| Networking | MetalLB, Cloudflare Tunnel |
| CI/CD | ArgoCD |
| And more... | n8n, Node-RED, MinIO, Home Assistant, ESPHome |

**Bundles** are pre-wired component combinations — ready-to-use
stacks. One exists today (Temporal + Postgres). More are coming.

## Quick start

```bash
# 1. Clone
git clone https://github.com/AItizate/forjate.git
cd forjate

# 2. Spin up a local cluster
cd k8s/overlays/ai-dev-stack
./01_init_cluster.sh

# 3. Deploy
./02_deploy.sh
```

15 minutes. A cluster with AI tools, auth, storage, ingress
and monitoring — running.

## Example overlays

| Overlay | What's inside |
|---------|---------------|
| `ai-dev-stack` | Base + OAuth2 + LiteLLM + vLLM + MinIO + Node-RED + Milvus |
| `cdc-event-sourcing` | Base + MongoDB + RabbitMQ + Debezium CDC |
| `agentic-orchestration` | Base + Temporal + MongoDB + Worker for multi-agent workflows |

## How it works

Kustomize handles everything. No templates, no magic variables.
Each overlay inherits the base and applies its patches on top.

```yaml
# Your overlay just says what it wants
resources:
  - ../../base
  - ../../components/apps/databases/postgres
  - ../../components/apps/ai-models/ollama
```

Want to change a hostname? A patch.
Add a secret? An `.env` file.
Enable a component? One line.

Remote tenants can consume the factory over SSH without living
in this repo:

```yaml
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=v1.0.0
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/databases/postgres?ref=v1.0.0
```

## Who this is for

For anyone who'd rather create than fight infrastructure.

Whether you're starting a side project, shipping an MVP,
or building out an entire organization's platform —
infra should be the enabler, not the bottleneck.

## Community

This is just another idea being shared. If it helps you create,
great.

Organizations that spend all their time fighting infra are
getting left behind. The ones that create, win.
Forjate is an attempt to lower that barrier.

Contributions welcome. Open an issue, send a PR,
or just use it and tell me how it went.

## License

[Apache 2.0](LICENSE)

# Example overlays

A small library of reference overlays. Each one is a concrete answer to a recurring question: _"how would Forjate look for **this** situation?"_

These docs are the design first. The implementation lives in `k8s/overlays/` (existing) and lands progressively in this repo as each design stabilizes.

| Overlay | Design doc | Implementation | Best for |
|---------|------------|----------------|----------|
| `ai-dev-stack` | — | [`k8s/overlays/ai-dev-stack/`](../../k8s/overlays/ai-dev-stack/) | Local AI development cluster (vLLM, Milvus, Node-RED, OAuth2) |
| `cdc-event-sourcing` | — | [`k8s/overlays/cdc-event-sourcing/`](../../k8s/overlays/cdc-event-sourcing/) | Event-driven services with Debezium-grade CDC and Mongo + RabbitMQ |
| `agentic-orchestration` | — | [`k8s/overlays/agentic-orchestration/`](../../k8s/overlays/agentic-orchestration/) | Temporal-orchestrated multi-agent workflows |
| `agentic-simple-workflow` | [doc](./agentic-simple-workflow.md) | [`k8s/overlays/agentic-simple-workflow/`](../../k8s/overlays/agentic-simple-workflow/) | The smallest production agentic stack — Postgres, MinIO, one worker |
| `home-edge-lab` | [doc](./home-edge-lab.md) | [`k8s/overlays/home-edge-lab/`](../../k8s/overlays/home-edge-lab/) | Raspberry + NAS home lab with IoT, cameras, RBAC, Google auth |
| `bare-metal-starter` | [doc](./bare-metal-starter.md) | [`k8s/overlays/bare-metal-starter/`](../../k8s/overlays/bare-metal-starter/) | First serious bare-metal cluster — k3s + Longhorn + MetalLB + Cloudflare Tunnel |
| `multi-cloud-portable` | [doc](./multi-cloud-portable.md) | [`k8s/overlays/multi-cloud-portable/`](../../k8s/overlays/multi-cloud-portable/) | One overlay, three clouds — abstract via Crossplane + StorageClass |
| `multi-tenant-pattern` | [doc](./multi-tenant-pattern.md) | [`k8s/overlays/multi-tenant-pattern/`](../../k8s/overlays/multi-tenant-pattern/) | Recursive pattern: base → org overlay → per-client overlay |

## Reading order

If you are new to Forjate, read them in this order:

1. **`bare-metal-starter`** — the absolute minimum that still feels production-grade.
2. **`agentic-simple-workflow`** — what a tiny SaaS-shaped overlay looks like on top of the base.
3. **`home-edge-lab`** — the same architecture compressed onto consumer hardware.
4. **`multi-tenant-pattern`** — how to repeat the pattern for N clients without duplicating code.
5. **`multi-cloud-portable`** — how to lift the same overlay across providers using Crossplane.

## How these docs are structured

Each overlay doc follows the same shape:

- **The situation** — what real problem the overlay is solving
- **Architecture** — diagram (link to `docs/assets/architecture/`)
- **Components used** — concrete list from the catalog
- **`kustomization.yaml`** — the actual file you would write
- **Notes** — gotchas, operational concerns, migration paths

Tight by design. If a doc grows beyond two screens, it should probably be split.

# Example overlays

A small library of reference overlays. Each one is a concrete answer to a recurring question: _"how would Forjate look for **this** situation?"_

Every overlay listed here meets at least Tier Mínimo of the [overlay convention](./CONVENTION.md) — design doc, diagram, README, and an entry in this table.

## Catalog

| Overlay | Tier | Design doc | Implementation | Diagram | Best for |
|---------|------|------------|----------------|---------|----------|
| `quickstart` | Advanced | [doc](./quickstart.md) | [`k8s/overlays/quickstart/`](../../k8s/overlays/quickstart/) | [png](../assets/architecture/overlay-quickstart.png) | Fresh-clone smoke test — k3d + Ollama + Gemma 4 + in-cluster validation Job |
| `ai-dev-stack` | Advanced | [doc](./ai-dev-stack.md) | [`k8s/overlays/ai-dev-stack/`](../../k8s/overlays/ai-dev-stack/) | [png](../assets/architecture/overlay-ai-dev-stack.png) | Local AI workbench on k3d — vLLM + Milvus + Node-RED + Open WebUI |
| `agentic-orchestration` | Advanced | [doc](./agentic-orchestration.md) | [`k8s/overlays/agentic-orchestration/`](../../k8s/overlays/agentic-orchestration/) | [png](../assets/architecture/overlay-agentic-orchestration.png) | Conversational agent + durable Temporal workflows, chat channels in front |
| `cdc-event-sourcing` | Advanced | [doc](./cdc-event-sourcing.md) | [`k8s/overlays/cdc-event-sourcing/`](../../k8s/overlays/cdc-event-sourcing/) | [png](../assets/architecture/overlay-cdc-event-sourcing.png) | MongoDB → Debezium → RabbitMQ CDC pipeline with end-to-end validation Job |
| `agentic-simple-workflow` | Recommended | [doc](./agentic-simple-workflow.md) | [`k8s/overlays/agentic-simple-workflow/`](../../k8s/overlays/agentic-simple-workflow/) | [png](../assets/architecture/overlay-agentic-simple-workflow.png) | Smallest production-shaped agentic stack — Postgres + MinIO + one agent |
| `bare-metal-starter` | Advanced | [doc](./bare-metal-starter.md) | [`k8s/overlays/bare-metal-starter/`](../../k8s/overlays/bare-metal-starter/) | [png](../assets/architecture/overlay-bare-metal-starter.png) | First serious bare-metal cluster + GitOps loop |
| `home-edge-lab` | Advanced | [doc](./home-edge-lab.md) | [`k8s/overlays/home-edge-lab/`](../../k8s/overlays/home-edge-lab/) | [png](../assets/architecture/overlay-home-edge-lab.png) | Pi + NAS home lab with IoT, cameras, family-chat agent |
| `multi-cloud-portable` | Recommended | [doc](./multi-cloud-portable.md) | [`k8s/overlays/multi-cloud-portable/`](../../k8s/overlays/multi-cloud-portable/) | [png](../assets/architecture/overlay-multi-cloud-portable.png) | One overlay, three clouds — Crossplane + StorageClass as portability seams |
| `multi-tenant-pattern` | Recommended | [doc](./multi-tenant-pattern.md) | [`k8s/overlays/multi-tenant-pattern/`](../../k8s/overlays/multi-tenant-pattern/) | [png](../assets/architecture/multi-tenant-pattern.png) | Recursive pattern: base → org overlay → per-client overlay |

## Use-case catalog

Overlays with a shorter life expectancy: brought up on demand, seeded, validated, thrown away. They live under `k8s/overlays/usecases/` and are driven by the [ephemeral runner](../../scripts/ephemeral/README.md) rather than by per-overlay bootstrap scripts. Design: [`docs/ephemeral-use-cases.md`](../ephemeral-use-cases.md).

| Use case | Isolation | Implementation | Diagram | What it proves |
|----------|-----------|----------------|---------|----------------|
| `db-migration-a-to-b` | shared | [`k8s/overlays/usecases/db-migration-a-to-b/`](../../k8s/overlays/usecases/db-migration-a-to-b/) | [prompt](../assets/architecture/ephemeral-usecases.prompt.md) _(png pending)_ | Reference scaffold — Postgres + MongoDB side by side, full lifecycle, migration deliberately left as a stub |

```bash
./scripts/ephemeral/ephemeral.sh up db-migration-a-to-b
./scripts/ephemeral/create-usecase.sh --name my-use-case
```

### What the tiers mean

- **Mínimo** — has the docs and diagram needed to understand it. Run it by hand.
- **Recommended** — adds namespace contract + hardening (probes, requests/limits, restricted securityContext) on every custom workload.
- **Advanced** — adds bootstrap scripts, per-namespace structure, and a validation Job that proves the overlay actually works post-deploy.

Full convention in [`CONVENTION.md`](./CONVENTION.md).

## Reading order

If you are new to Forjate, read them in this order:

0. **`quickstart`** — before anything else. The smoke test that answers "does this work on my laptop?" before you invest in any of the others.
1. **`bare-metal-starter`** — the absolute minimum that still feels production-grade.
2. **`agentic-simple-workflow`** — what a tiny SaaS-shaped overlay looks like on top of the base.
3. **`agentic-orchestration`** — when the agent has to do durable, multi-step work and chat with humans through Telegram or WhatsApp.
4. **`home-edge-lab`** — the same patterns compressed onto consumer hardware.
5. **`multi-tenant-pattern`** — how to repeat any of the above for N clients without duplicating code.
6. **`multi-cloud-portable`** — how to lift the same overlay across providers using Crossplane.
7. **`ai-dev-stack`** — the local-laptop AI workbench, when you just want to prototype.
8. **`cdc-event-sourcing`** — when downstream consumers need a stream of every mutation, not just a final state.

## How these docs are structured

Each overlay doc follows the same shape (see [`CONVENTION.md`](./CONVENTION.md) for the template):

- **The situation** — what real problem the overlay solves
- **Architecture** — diagram from `docs/assets/architecture/`
- **Components used** — concrete list from the catalog
- **`kustomization.yaml`** — the essential shape of the actual file
- **Notes** — gotchas, operational concerns, migration paths

Tight by design. If a doc grows beyond two screens, it gets split.

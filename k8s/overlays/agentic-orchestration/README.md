# `agentic-orchestration`

Temporal-orchestrated agentic workflows. Postgres + MongoDB + a worker container that connects to LiteLLM from `base`.

Full design in [`docs/overlays/agentic-orchestration.md`](../../../docs/overlays/agentic-orchestration.md).

## Before deploying

1. Replace `image: registry.example.com/temporal-worker:latest` in `namespaces/agentic/worker-deployment.yaml` with your own worker image that registers your workflows, activities, and skills.
2. Copy each `secrets/*.env.example` and `namespaces/agentic/secrets/*.env.example` to the corresponding `.env` and fill in real values.

## Build & deploy

```bash
kubectl kustomize k8s/overlays/agentic-orchestration | kubectl apply -f -
```

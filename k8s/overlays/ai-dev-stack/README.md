# `ai-dev-stack`

Local AI workbench on k3d — vLLM + Milvus + Node-RED + Open WebUI, behind one sign-in.

Full design in [`docs/overlays/ai-dev-stack.md`](../../../docs/overlays/ai-dev-stack.md).

## Spin up

```bash
./01_init_cluster.sh   # creates a 2-node k3d cluster
./02_deploy.sh         # applies the overlay + bootstraps Helm dependencies
```

## Tear down

```bash
./destroy_cluster.sh
```

## Before deploying

Edit the `.env` files under `secrets/` and `namespaces/*/secrets/` — copy each `.env.example` to its `.env` sibling and fill in real values.

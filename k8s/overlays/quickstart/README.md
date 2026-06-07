# `quickstart`

The shortest path from a fresh clone to a working Forjate cluster: **k3d + Ollama + Gemma 4 E2B (quantized)**.

No external secrets, no OAuth setup, no cloud accounts. One model, one validation, one teardown.

## What you get

- A local 2-node k3d cluster
- Ollama running in `ai-tools`
- `gemma4:e2b-it-q4_K_M` pulled and ready to answer prompts via the Ollama HTTP API

## Requirements

- `k3d` ≥ 5.6
- `kubectl`
- `curl`, `python3` (for validation)
- ~10 GB free disk (model is ~7 GB + image layers)
- ~10 GB free RAM (the Ollama container limit)

Gemma 4 E2B is multimodal and ships as a single ~7 GB blob even in the Q4 tag — it eats real RAM. If you don't have 10 GB headroom on your laptop, switch to a lighter model:

```bash
OLLAMA_MODEL=gemma3:1b ./02_deploy.sh
OLLAMA_MODEL=gemma3:1b ./03_validate.sh
```

## Spin up

```bash
./01_init_cluster.sh   # k3d cluster: 1 server + 1 agent
./02_deploy.sh         # apply overlay + ollama pull gemma4:e2b-it-q4_K_M
./03_validate.sh       # node check + prompt round-trip
```

Expected wall-clock: **20–30 minutes** on a decent connection (model is ~7 GB). The first prompt response can take **1–3 minutes** on CPU while the model warms up — subsequent prompts are faster.

After `03_validate.sh`, you'll have a port-forward instructions printed to talk to the model from your laptop.

## Tear down

```bash
./destroy.sh
```

Removes the k3d cluster and the kubeconfig file at `~/.kube/forjate-quickstart.yaml`.

## What's intentionally not here

This overlay is a smoke test of the factory — proof that base + a component compose and reach a usable state. It deliberately omits:

- ingress + TLS (validation uses port-forward)
- auth (`oauth2-proxy`, Google OAuth)
- LiteLLM, Open WebUI, vLLM (see `ai-dev-stack` for a richer local AI workbench)
- Longhorn, MinIO (k3d's `local-path` is enough)

For a production-like local dev stack with all of the above, see [`../ai-dev-stack/`](../ai-dev-stack/).

## Tuning

Environment variables understood by the scripts:

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:e2b-it-q4_K_M` | Model tag to pull and test |
| `PULL_TIMEOUT_SECONDS` | `900` | Max time for `ollama pull` |
| `LOCAL_PORT` | `11434` | Port used for `kubectl port-forward` |
| `PROMPT` | `Reply with exactly: hello from forjate` | Validation prompt |

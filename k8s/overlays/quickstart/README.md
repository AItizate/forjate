# `quickstart`

The shortest path from a fresh clone to a working Forjate cluster: **base + LiteLLM (OpenAI-compatible gateway) → Ollama (local runtime) → Gemma 4 E2B (quantized)**.

No external API keys, no OAuth, no cloud accounts. One inference gateway, one model runtime, one validation Job, one teardown.

## What you get

- A local 2-node k3d cluster running the minimal Forjate base (Traefik, cert-manager namespace, MinIO operator)
- **Ollama** in `ai-tools` namespace, with `gemma4:e2b-it-q4_K_M` pulled and warm
- **LiteLLM** in front, exposing an **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`) that proxies to Ollama
- An in-cluster validation Job that hits the LiteLLM endpoint end-to-end

## Requirements

- `k3d` ≥ 5.6
- `kubectl`
- Docker daemon running
- ~10 GB free disk (model is ~7 GB + image layers)
- ~10 GB free RAM (Ollama container limit + LiteLLM + base overhead)

Gemma 4 E2B is multimodal and ships as a single ~7 GB blob even in the Q4 tag — it eats real RAM. If you don't have 10 GB headroom on your laptop, switch to a lighter model:

```bash
OLLAMA_MODEL=gemma3:1b ./02_deploy.sh
OLLAMA_MODEL=gemma3:1b ./03_validate.sh
```

## Spin up

```bash
./01_init_cluster.sh   # k3d cluster: 1 server + 1 agent
./02_deploy.sh         # base + ollama + litellm + ollama pull + warmup + validation Job
./03_validate.sh       # wait for the Job, print its output
```

Expected wall-clock: **20–30 minutes** with the default Gemma 4 (most of it is the model download). With `OLLAMA_MODEL=gemma3:1b`, ~5 minutes total. The first prompt response can take 1–3 minutes on CPU while the model warms up — `02_deploy.sh` does the warmup so `03_validate.sh` only pays "generate".

After validation, `03_validate.sh` prints a ready-to-paste port-forward + curl pair so you can talk to the model from your laptop.

## How to talk to the model

The validation Job already proved the pipeline works. For interactive use:

```bash
kubectl -n ai-tools port-forward svc/litellm 4000:4000
```

Then in another terminal (LiteLLM speaks the OpenAI Chat Completions API):

```bash
curl http://localhost:4000/v1/chat/completions \
  -H 'Authorization: Bearer sk-quickstart-localdev-only' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma",
    "messages": [{"role": "user", "content": "Explica forjate en una frase"}]
  }'
```

Available model aliases (defined in `namespaces/ai-tools/configs/litellm-config.yaml`):
- `gemma` → `ollama/gemma4:e2b-it-q4_K_M`
- `gemma3` → `ollama/gemma3:1b`

You can also bypass LiteLLM and hit Ollama directly:

```bash
kubectl -n ai-tools port-forward svc/ollama-service 11434:11434
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma4:e2b-it-q4_K_M","prompt":"Hello","stream":false}'
```

## Tear down

```bash
./destroy.sh
```

Removes the k3d cluster and the kubeconfig file at `~/.kube/forjate-quickstart.yaml`. Volumes go with the cluster — the next `02_deploy.sh` re-downloads the model.

## About the LiteLLM master key

`secrets/litellm.env` ships a hardcoded master key `sk-quickstart-localdev-only`. **This is safe to commit** because the cluster runs on k3d with no external ingress, the LiteLLM Service is `ClusterIP` only, and the key only authenticates the in-cluster validation Job. Real environments use SealedSecrets / Vault / an external secret store — never a committed literal.

## What's intentionally not here

- **Ingress + TLS** — validation uses port-forward, Traefik is in the base but no Ingress objects.
- **OAuth / authn for humans** — the validation Job uses the master key directly.
- **Postgres for LiteLLM** — `STORE_MODEL_IN_DB=False`. You lose admin UI persistence, model store, request logs. The `ai-dev-stack` and `agentic-orchestration` overlays opt in to `litellm/postgres` if you want all that.
- **Open WebUI, vLLM** — see `ai-dev-stack` for a richer local AI workbench.
- **Longhorn** — k3d's `local-path` is enough. Longhorn is a `components/apps/storage/` choice.

For a production-like local dev stack with all of the above, see [`../ai-dev-stack/`](../ai-dev-stack/).

## Tuning

Environment variables understood by the scripts:

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:e2b-it-q4_K_M` | Model tag to pull into Ollama. The script maps known values (`gemma3:1b`, `gemma4:e2b-it-q4_K_M`) to the corresponding LiteLLM alias automatically. |
| `LITELLM_MODEL_ALIAS` | (auto from `OLLAMA_MODEL`) | Override the LiteLLM `model_name` the validation Job tests against. Set when you add a new model to `litellm-config.yaml`. |
| `PULL_TIMEOUT_SECONDS` | `900` | Max time for `ollama pull` |
| `WAIT_TIMEOUT` | `900s` | Max time `03_validate.sh` waits for the Job |

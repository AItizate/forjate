# `quickstart`

The shortest path from a fresh clone to a working Forjate cluster: **base + LiteLLM (OpenAI-compatible gateway) → Ollama (local runtime) → Gemma 3 1B**.

No external API keys, no OAuth, no cloud accounts. One inference gateway, one model runtime, one validation Job, one teardown. Five minutes end-to-end on a decent connection.

## What you get

- A local 2-node k3d cluster running the minimal Forjate base (Traefik, cert-manager namespace, MinIO operator)
- **Ollama** in `ai-tools` namespace, with `gemma3:1b` pulled and warm
- **LiteLLM** in front, exposing an **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`) that proxies to Ollama
- An in-cluster validation Job that hits the LiteLLM endpoint end-to-end

## Requirements

- `k3d` ≥ 5.6
- `kubectl`
- Docker daemon running
- ~2 GB free disk (model is ~815 MB + image layers)
- ~4 GB free RAM (Ollama ~2 GB + LiteLLM + base overhead)

## Spin up

```bash
./01_init_cluster.sh   # k3d cluster: 1 server + 1 agent
./02_deploy.sh         # base + ollama + litellm + ollama pull + warmup + validation Job
./03_validate.sh       # wait for the Job, print its output
```

Expected wall-clock: **~5 minutes** end-to-end with the default `gemma3:1b`. After validation, `03_validate.sh` prints a ready-to-paste port-forward + curl pair to talk to the model from your laptop.

### Want a heavier, multimodal model?

`gemma4:e2b-it-q4_K_M` is Gemma 4 Edge 2B — multimodal, ~7 GB on disk, ~8 GB RAM. Override and re-run:

```bash
OLLAMA_MODEL=gemma4:e2b-it-q4_K_M ./02_deploy.sh
OLLAMA_MODEL=gemma4:e2b-it-q4_K_M ./03_validate.sh
```

Wall-clock jumps to **20–30 min** because of the download. The first prompt on CPU can take 1–3 min to load the model into RAM — `02_deploy.sh` warms it during deploy so `03_validate.sh` only pays "generate".

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
    "model": "gemma3",
    "messages": [{"role": "user", "content": "Explica forjate en una frase"}]
  }'
```

The master key is committed in `namespaces/ai-tools/configs/litellm-config.yaml` — see "About auth" below.

Available model aliases (defined in `namespaces/ai-tools/configs/litellm-config.yaml`):
- `gemma3` → `ollama/gemma3:1b` (default)
- `gemma` → `ollama/gemma4:e2b-it-q4_K_M`

You can also bypass LiteLLM and hit Ollama directly:

```bash
kubectl -n ai-tools port-forward svc/ollama-service 11434:11434
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma3:1b","prompt":"Hello","stream":false}'
```

## Tear down

```bash
./destroy.sh
```

Removes the k3d cluster and the kubeconfig file at `~/.kube/forjate-quickstart.yaml`. Volumes go with the cluster — the next `02_deploy.sh` re-downloads the model.

## About auth

The quickstart configures a **demo master key** for LiteLLM (`sk-quickstart-localdev-only`), hardcoded in `namespaces/ai-tools/configs/litellm-config.yaml` under `general_settings.master_key`. Safe to commit: the cluster runs on k3d with no external ingress and the Service is `ClusterIP`. Real tenants seal real secrets.

**The key has to live in the config YAML, not in `LITELLM_MASTER_KEY` env var.** LiteLLM treats env-var keys as "virtual keys" that need a Postgres lookup, which the quickstart deliberately skips — so an env-var key 401s every external request even when correct. `general_settings.master_key` is the "proxy admin master" path and works without a DB.

`ai-dev-stack` and `agentic-orchestration` are the overlays where this gets serious — they opt in to `components/apps/ai-models/litellm/postgres`, manage real keys via SealedSecrets, and put OAuth2 Proxy in front of the human-facing UIs.

## What's intentionally not here

- **Ingress + TLS** — validation uses port-forward, Traefik is in the base but no Ingress objects.
- **OAuth / authn for humans** — no `oauth2-proxy`. The LiteLLM master key is for the validation Job and your local curls, nothing else.
- **Postgres for LiteLLM** — `STORE_MODEL_IN_DB=False`, no `envFrom`. You lose admin UI persistence, virtual key management, request logs. `ai-dev-stack` and `agentic-orchestration` opt in to `litellm/postgres` if you want all that.
- **Open WebUI, vLLM** — see `ai-dev-stack` for a richer local AI workbench.
- **Longhorn** — k3d's `local-path` is enough. Longhorn is a `components/apps/storage/` choice.

For a production-like local dev stack with all of the above, see [`../ai-dev-stack/`](../ai-dev-stack/).

## Tuning

Environment variables understood by the scripts:

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `gemma3:1b` | Model tag to pull into Ollama. The script maps known values (`gemma3:1b`, `gemma4:e2b-it-q4_K_M`) to the corresponding LiteLLM alias automatically. |
| `LITELLM_MODEL_ALIAS` | (auto from `OLLAMA_MODEL`) | Override the LiteLLM `model_name` the validation Job tests against. Set when you add a new model to `litellm-config.yaml`. |
| `PULL_TIMEOUT_SECONDS` | `900` | Max time for `ollama pull` |
| `WAIT_TIMEOUT` | `900s` | Max time `03_validate.sh` waits for the Job |

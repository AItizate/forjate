# Overlay: `quickstart`

> The shortest path from `git clone` to a cluster with an LLM answering prompts behind an OpenAI-compatible gateway. No external API keys, no OAuth, no cloud accounts.

## The situation

You've just cloned Forjate and you want to know one thing: **does this actually work on my laptop?** Not "is the architecture sound", not "can I deploy LiteLLM with five API keys" — just _stand it up and let me see the LLM say hello_.

The other overlays in the catalog are designed for what comes after that question. `ai-dev-stack` runs a full local AI workbench but expects a Google OAuth app, a Cloudflare DNS token, an LLM provider API key, and five `.env` files you copy from `.env.example`. `bare-metal-starter` assumes you own the metal. `agentic-orchestration` assumes you have a workflow to orchestrate.

`quickstart` exists for the step before all of those: prove the factory composes into a working cluster on a fresh laptop in **five minutes**, with zero credentials and one open question — _is the LLM responding?_ The post-deploy validation Job answers that question with a real `POST /v1/chat/completions` round-trip through **LiteLLM in front of Ollama serving Gemma 3 1B** — the same gateway shape every Forjate tenant uses in production, just with a single local backend instead of a panel of cloud providers. If the Job exits 0, the pipeline is honest.

## Architecture

![Quickstart](../assets/architecture/overlay-quickstart.png)

## Components used

| Component | Why |
|-----------|-----|
| `../../base` | Traefik, cert-manager, MinIO operator, namespaces. The minimal foundation every Forjate cluster ships. |
| `apps/ai-models/ollama` | Local LLM runtime. CPU-friendly, GGUF models, one HTTP API on port 11434. |
| `apps/ai-models/litellm` (no postgres) | OpenAI-compatible gateway in front of Ollama. Same component every production tenant uses — quickstart just configures one local backend instead of cloud providers. |
| `quickstart-validate-job.yaml` | In-cluster smoke test — hits `/health/liveliness`, `/v1/models`, and `/v1/chat/completions` against LiteLLM. |

The quickstart is the **first honest client** of the minimal base. LiteLLM here runs without Postgres (`STORE_MODEL_IN_DB=False`, no `litellm-postgres-secret`) — overlays that want the admin UI persistence, model store, or request logs opt in to `litellm/postgres` separately (`ai-dev-stack` and `agentic-orchestration` do).

## `kustomization.yaml`

```yaml
# k8s/overlays/quickstart/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base
  - ./namespaces/ai-tools

# k8s/overlays/quickstart/namespaces/ai-tools/kustomization.yaml
namespace: ai-tools

resources:
  - ../../../../components/apps/ai-models/ollama
  - ../../../../components/apps/ai-models/litellm
  - quickstart-validate-job.yaml

configMapGenerator:
  - name: litellm-config-file                  # override the upstream LiteLLM config
    files: [config.yaml=configs/litellm-config.yaml]
    behavior: replace

patches:
  - path: patches/ollama-pvc-size.yaml         # 1Gi → 10Gi (fits gemma3:1b and gemma4 alike)
    target: { kind: PersistentVolumeClaim, name: pvc-ollama }
  - path: patches/ollama-resources.yaml        # requests 2Gi (gemma3:1b), limit 10Gi (gemma4 headroom)
    target: { kind: StatefulSet, name: ollama }
  - path: patches/litellm-no-auth.yaml         # STORE_MODEL_IN_DB=False + drop envFrom (no master key, no DB)
    target: { kind: Deployment, name: litellm }
```

The LiteLLM config (`configs/litellm-config.yaml`) declares two aliases pointing to Ollama:

```yaml
model_list:
  - model_name: "gemma"
    litellm_params:
      model: "ollama/gemma4:e2b-it-q4_K_M"
      api_base: "http://ollama-service.ai-tools.svc.cluster.local:11434"
  - model_name: "gemma3"
    litellm_params:
      model: "ollama/gemma3:1b"
      api_base: "http://ollama-service.ai-tools.svc.cluster.local:11434"
```

The default `OLLAMA_MODEL=gemma3:1b` matches the `gemma3` alias. Override with `OLLAMA_MODEL=gemma4:e2b-it-q4_K_M` for the heavier multimodal model.

## Notes

- **The default model is `gemma3:1b`** — ~815 MB on disk, ~2 GB in RAM. End-to-end runs in ~5 minutes on a decent connection. For multimodal capability, override `OLLAMA_MODEL=gemma4:e2b-it-q4_K_M` (Gemma 4 E2B, 7.2 GB on disk, ~8 GB in RAM, ~20–30 min wall-clock). `02_deploy.sh` maps `OLLAMA_MODEL` to the matching LiteLLM alias automatically.
- **Master key lives in the config, not in an env var.** The committed `general_settings.master_key: sk-quickstart-localdev-only` in `configs/litellm-config.yaml` is what LiteLLM treats as "the proxy admin master" (no DB required). Setting `LITELLM_MASTER_KEY` as an env var instead routes the same key through LiteLLM's virtual-key validation path, which needs Postgres — without it, every external request 401s even when the key matches. The deployment patch deliberately removes `envFrom` so no key leaks via env. Safe to commit because the cluster is k3d / ClusterIP only.
- **First prompt is slow on CPU for larger models.** gemma3:1b is responsive in seconds even cold. Gemma 4 E2B takes 1–3 min to load 7 GB into RAM the first time. `02_deploy.sh` warms Ollama directly during deploy so the validation Job pays only "generate", not "load + generate".
- **`OLLAMA_HOST=0.0.0.0` gotcha.** The Ollama image sets this so `ollama serve` listens on all interfaces. The CLI inherits it and then tries to dial `0.0.0.0` as a client address, which fails. Every `kubectl exec` in `02_deploy.sh` overrides it to `127.0.0.1:11434`.
- **No ingress, no TLS, no human auth.** Validation runs entirely inside the cluster (the Job calls `litellm.ai-tools.svc.cluster.local:4000`). To talk to the model from your laptop, port-forward — instructions printed by `03_validate.sh`.
- **No persistent volume between runs of `destroy.sh`.** Tearing down deletes the k3d cluster and its volumes, so the next `02_deploy.sh` re-downloads the model.

## Reading the validation Job

```bash
kubectl -n ai-tools logs job/quickstart-validate
```

It runs three checks: LiteLLM health, the model alias is present in `/v1/models`, and a real chat completion round-trip via `/v1/chat/completions`. Prints `[PASS]` / `[FAIL]` per check, exits non-zero on any failure. `ttlSecondsAfterFinished: 600` cleans it up automatically.

## Migration path

`quickstart` is a smoke test, not a destination. Once it's green you've confirmed the factory works on your machine — pick the overlay that matches your actual problem:

- A local AI workbench with multiple models and a real UI → [`ai-dev-stack`](./ai-dev-stack.md).
- A first bare-metal cluster with TLS, GitOps, monitoring → [`bare-metal-starter`](./bare-metal-starter.md).
- Chat-first agents with durable workflows → [`agentic-orchestration`](./agentic-orchestration.md).

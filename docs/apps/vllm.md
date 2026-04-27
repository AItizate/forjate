# vLLM

**Official Website:** [https://docs.vllm.ai/](https://docs.vllm.ai/)
**GitHub:** [https://github.com/vllm-project/vllm](https://github.com/vllm-project/vllm)

## Purpose in Architecture

`vLLM` is a high-performance inference engine for large language models. It replaces or complements [Ollama](./ollama.md) as the model serving layer, targeting production workloads where throughput, concurrency, and GPU efficiency matter.

While Ollama is ideal for development and single-user scenarios, vLLM is designed for multi-user, high-throughput environments. It achieves this through innovations like **PagedAttention** (reduces VRAM waste from ~60-80% to <4%), **continuous batching** (dynamic request scheduling instead of sequential processing), and **prefix caching** (reuses KV cache across requests sharing the same system prompt).

## Basic Operation

- **Model Server:** vLLM loads a model from HuggingFace into GPU memory and exposes it through an OpenAI-compatible API on port 8000.
- **OpenAI-Compatible API:** Serves `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, and `/health` endpoints — fully compatible with the OpenAI Python client.
- **Model Configuration:** The model to serve, context length, GPU memory utilization, data type, and quantization are configured via a `ConfigMap`.
- **Quantization Support:** Supports FP8, INT4, INT8, GPTQ, AWQ, and GGUF formats for running larger models on limited VRAM.

## Project Integration

- **Component:** The component is located in `k8s/components/apps/ai-models/vllm/`. It deploys vLLM as a `StatefulSet` with a `ConfigMap` for model configuration.
- **Model Storage:** Models are downloaded from HuggingFace on first load. A `PersistentVolumeClaim` (50Gi by default) caches them at `/data/huggingface` to avoid re-downloading on pod restarts. This volume is provided by our storage solution, such as [Longhorn](./longhorn.md).
- **Service Exposure:** vLLM is exposed internally via a Kubernetes `Service` (`vllm-service.ai-tools.svc.cluster.local:8000`). It is not publicly exposed to the internet.
- **Consumption by LiteLLM:** The main consumer is [LiteLLM](./litellm.md). Since vLLM exposes an OpenAI-compatible API, LiteLLM can route to it using the `openai/` provider prefix pointing to the internal service URL. This allows `Open WebUI` and other clients to use vLLM-served models through LiteLLM's unified interface.
- **GPU Requirement:** Unlike Ollama, vLLM requires at least one NVIDIA GPU (Compute Capability 7.0+: V100, T4, A100, H100). The `StatefulSet` requests `nvidia.com/gpu: "1"` by default. In clusters with GPU nodes, `nodeSelector` and `tolerations` should be added via overlay patches.
- **Health Probes:** The `StatefulSet` includes readiness (60s initial delay) and liveness (120s initial delay) probes against `/health`, accounting for the time needed to load models into GPU memory.

## Customization via Overlays

Tenants can patch the `vllm-config` ConfigMap to adjust:

| Key | Default | Description |
|-----|---------|-------------|
| `MODEL_NAME` | `google/gemma-4-E2B-it` | HuggingFace model ID |
| `MAX_MODEL_LEN` | `4096` | Maximum context length |
| `GPU_MEMORY_UTILIZATION` | `0.9` | Fraction of GPU memory to use |
| `DTYPE` | `auto` | Data type (`auto`, `float16`, `bfloat16`) |
| `QUANTIZATION` | `` | Quantization method (`awq`, `gptq`, `fp8`, or empty) |

For private or gated models (e.g., Llama), a HuggingFace token must be provided via a Secret and injected as the `HF_TOKEN` environment variable.

## Ollama vs vLLM

| | Ollama | vLLM |
|---|---|---|
| **Use case** | Development, single user | Production, multiple users |
| **GPU** | Optional | Required (V100+) |
| **Concurrency** | Sequential | Continuous batching |
| **Model source** | Ollama library (`ollama pull`) | HuggingFace Hub |
| **API** | Ollama REST API | OpenAI-compatible |
| **Quantization** | GGUF | FP8, GPTQ, AWQ, INT4/8 |

Both components can coexist — tenants choose one or both depending on their hardware and workload needs.

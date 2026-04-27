# Ollama

**Official Website:** [https://ollama.com/](https://ollama.com/)

## Purpose in Architecture

`Ollama` is a tool that greatly simplifies running and managing open-source large language models (LLMs), such as Llama 3, Mistral, or Phi, on our own hardware. Its role is to **serve the local language models**, exposing them via a REST API so that other applications can consume them.

It is the engine that powers the generative AI capabilities of our local stack.

## Basic Operation

-   **Model Server:** Ollama runs as a service that loads language models into memory (or VRAM if GPUs are available) and exposes them through an API.
-   **Model Management:** It provides a simple CLI to download, list, and remove models from its official library (`ollama pull llama3`).
-   **REST API:** It exposes endpoints for generating text, embeddings, and chatting with the loaded models.

## Project Integration

-   **Base:** The base configuration for deploying Ollama as a `StatefulSet` is located in `k8s/base/apps/ollama/`. We use a `StatefulSet` to prepare for future expansions and to ensure each pod has a stable network identity.
-   **Model Storage:** Language models can be very large. To avoid having to download them every time a pod restarts, Ollama uses a `PersistentVolumeClaim` to store the downloaded models on a persistent volume. This volume is provided by our storage solution, such as [Longhorn](./longhorn.md).
-   **Service Exposure:** Ollama is exposed internally in the cluster via a Kubernetes `Service` (`ollama-service.ai-tools.svc.cluster.local`). It is not publicly exposed to the internet.
-   **Consumption by LiteLLM:** The main consumer of Ollama is [LiteLLM](./litellm.md). In the LiteLLM configuration, we define the Ollama models by pointing to the internal Ollama service. This allows `Open WebUI` and other client applications to use the local models through LiteLLM's unified interface.
-   **GPU Allocation (Optional):** In clusters with GPU-enabled nodes, `nodeSelector` and `tolerations` can be added in the `overlays` to ensure that Ollama pods run on those nodes and can take advantage of hardware acceleration.

In summary, `Ollama` is the component that allows us to have sovereignty over our AI models, running them efficiently on our own infrastructure.

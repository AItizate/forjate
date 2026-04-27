# LiteLLM

**Official Website:** [https://litellm.ai/](https://litellm.ai/)

## Purpose in Architecture

`LiteLLM` (Lite Local Language Model) is a key component in our AI stack. It acts as a **proxy and load balancer** that provides a consistent, OpenAI-compatible API interface for interacting with a wide variety of large language models (LLMs), both local and remote.

Its main function is to decouple our applications (like [Open WebUI](./open-webui.md)) from the implementation details of the language models.

## Basic Operation

-   **Unified Interface:** It exposes an API endpoint that mimics the OpenAI API (`/v1/chat/completions`). This allows any OpenAI-compatible client (including `Open WebUI`) to use it without changes.
-   **Model Routing:** `LiteLLM` reads a configuration file (`config.yaml`) where all available models are defined. When it receives a request for a specific model (e.g., `ollama/llama3`), it routes the request to the corresponding backend.
-   **Load Balancing and Failover:** It can manage multiple instances of the same model, distributing the load among them and handling failures.
-   **Logging and Metrics:** It centralizes the logging of all LLM calls, which is useful for observability and auditing.

## Project Integration

-   **Base Configuration:** Located in `k8s/base/apps/litellm/`.
-   **Central Configuration:** The `ConfigMap` containing LiteLLM's `config.yaml` is the heart of its configuration. This is managed in the `overlays` (`k8s/overlays/<tenant>/configs/litellm-config.yaml`), as the list of available models is specific to each tenant.
-   **Connection to LLMs:**
    -   For local models, it connects to the [Ollama](./ollama.md) service (`ollama-service.ai-tools.svc.cluster.local`).
    -   For external models, it is configured with the API URLs and necessary credentials, which are securely injected via `Secrets`.
-   **Exposure:** `LiteLLM` is not normally exposed outside the cluster. Applications like `Open WebUI` interact with it through its internal Kubernetes service name.

In summary, `LiteLLM` is the "brain" that decides which language model each request is sent to, providing flexibility and scalability to our AI platform.

> For more details on its configuration in a tenant, see the [LiteLLM Configuration Guide](../tenant-onboarding/configuring-litellm.md).

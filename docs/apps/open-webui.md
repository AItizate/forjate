# Open WebUI

**Official Website:** [https://open-webui.com/](https://open-webui.com/)

## Purpose in Architecture

`Open WebUI` is an intuitive and feature-rich chat web user interface designed for interacting with large language models (LLMs). Originally known as "Ollama WebUI," it has evolved to be compatible with multiple LLM backends.

Its role in our project is to provide the **main user interface for end-users to interact with our generative AI stack**. It is the "frontend" of our chat service.

## Basic Operation

-   **Chat Interface:** Provides a user-friendly, ChatGPT-like experience.
-   **OpenAI API Compatible:** `Open WebUI` is designed to talk to backends that expose an OpenAI-compatible API. This makes it a perfect fit for integrating with [LiteLLM](./litellm.md).
-   **User and Document Management:** Allows for user management, chat history, and the ability to import documents for RAG (Retrieval-Augmented Generation).
-   **Customization:** Allows users to adjust model parameters, use system prompts, and organize their conversations.

## Project Integration

-   **Base:** The base configuration for `Open WebUI` is located in `k8s/base/apps/open-webui/`.
-   **Backend Configuration:** `Open WebUI` is configured to point to the internal `LiteLLM` service (`litellm.ai-tools.svc.cluster.local`). It does not connect directly to `Ollama`. This configuration is done via environment variables in its `Deployment`, which can be patched in the `overlays`.
-   **Persistence:** It uses a `PersistentVolumeClaim` to store its internal database, which contains users, chat histories, and documents. This volume is provided by our storage solution, such as [Longhorn](./longhorn.md).
-   **Exposure and Security:**
    -   It is exposed to the outside world via an `Ingress` managed by [Traefik](./traefik.md).
    -   Access is protected by [oauth2-proxy](./oauth2-proxy.md), ensuring that only authenticated users can access the chat interface. The hostname (`chat.tenant.com`) is defined in the `overlay`.

`Open WebUI` is the visible face of our AI service, providing a polished and powerful user experience on top of the `Ollama` and `LiteLLM` infrastructure.

> For more details on its configuration in a tenant, see the [Open WebUI Configuration Guide](../tenant-onboarding/configuring-open-webui.md).

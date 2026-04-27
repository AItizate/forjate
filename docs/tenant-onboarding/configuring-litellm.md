# Configuring LiteLLM for a New Tenant

LiteLLM acts as a proxy to various Large Language Models (LLMs). Its configuration is managed on a per-tenant basis, allowing each tenant to have a unique set of models, routing strategies, and API keys.

## Configuration Steps

To configure LiteLLM for a new tenant, you need to edit two files within the tenant's overlay directory.

### 1. Define Models and Routing (`litellm-config.yaml`)

This file controls the core behavior of LiteLLM.

1.  **Locate the File**: Open `k8s/overlays/{tenant-name}/configs/litellm-config.yaml`.
2.  **Edit the Configuration**: Modify the `model_list` to define which models the tenant can access. You can specify models from providers like OpenAI, Anthropic, Gemini, etc.

    The configuration should reference environment variables for API keys, which will be provided by a Kubernetes secret.

    **Example**:
    ```yaml
    model_list:
      - model_name: "gpt-4"
        litellm_params:
          model: "openai/gpt-4"
          api_key: os.environ/OPENAI_API_KEY
      - model_name: "claude-3-opus"
        litellm_params:
          model: "anthropic/claude-3-opus-20240229"
          api_key: os.environ/ANTHROPIC_API_KEY
    ```

### 2. Provide API Keys (`litellm.env`)

This file provides the actual secret values for the API keys referenced in the configuration file.

1.  **Locate the File**: Open `k8s/overlays/{tenant-name}/secrets/litellm.env`.
2.  **Add API Keys**: Add the API keys for each provider you configured in `litellm-config.yaml`. The environment variable names **must** match the ones used in the `os.environ/...` references.

    **Example**:
    ```env
    # k8s/overlays/my-tenant/secrets/litellm.env
    OPENAI_API_KEY="sk-..."
    ANTHROPIC_API_KEY="sk-ant-..."
    ```

### How It Works

The `kustomization.yaml` for the tenant uses a `configMapGenerator` and a `secretGenerator` to automatically create a `ConfigMap` and a `Secret` in Kubernetes from these two files. The LiteLLM deployment then mounts this configuration and these secrets, making the models available to other applications in the cluster.

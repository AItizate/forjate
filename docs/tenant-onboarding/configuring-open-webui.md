# Configuring Open WebUI for a New Tenant

Open WebUI provides the user interface for interacting with the backend Language Models. Its configuration is managed on a per-tenant basis, primarily to ensure it connects to the correct LLM backend (e.g., the tenant's specific LiteLLM instance).

## Configuration via Environment Patch

Unlike other applications that use ConfigMaps or Helm values, Open WebUI's base deployment is customized using a Kustomize patch that modifies its environment variables.

### 1. Locate the Environment Patch

The patch file is located at:
`k8s/overlays/{tenant-name}/patches/open-webui-env-patch.yaml`

### 2. Understand the Configuration

This patch file directly sets environment variables on the Open WebUI deployment. The most critical variable is `OLLAMA_BASE_URL`.

**Example Patch**:
```yaml
# k8s/overlays/my-tenant/patches/open-webui-env-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
spec:
  template:
    spec:
      containers:
      - name: open-webui
        env:
        - name: OLLAMA_BASE_URL
          value: "http://litellm.ai-tools.svc.cluster.local:4000"
```

### Action Required

1.  **Verify the Backend URL**: For a new tenant, you must ensure that the `value` of the `OLLAMA_BASE_URL` environment variable correctly points to the tenant's LiteLLM service. The standard internal Kubernetes DNS name is `http://litellm.{namespace}.svc.cluster.local:{port}`. By default, LiteLLM is deployed in the `ai-tools` namespace and listens on port `4000`.
2.  **Add Other Variables (Optional)**: You can set other Open WebUI environment variables by adding them to the `env` list in this patch file if needed.

### How It Works

The tenant's `kustomization.yaml` applies this patch to the base `open-webui` deployment. This dynamically changes the environment variables for the tenant's instance, redirecting it to the correct backend without altering the base manifests.

### 3. Additional Configurations

Besides environment variables, the tenant overlay typically customizes other aspects of the Open WebUI deployment via patches:

-   **Ingress Configuration (`open-webui-ingress-patch.yaml`):** This patch is used to set the hostname on the Ingress resource, which defines how the application is exposed to the internet (e.g., `webui.tenant.com`).
-   **Affinity Patch (`open-webui-affinity-patch.yaml`):** This patch modifies the deployment's affinity rules, allowing you to control on which Kubernetes nodes the Open WebUI pods should run. This is useful for performance tuning or node-specific scheduling.

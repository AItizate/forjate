# Configuring oauth2-proxy for a New Tenant

The `oauth2-proxy` application is managed via a Helm chart, and its configuration is controlled on a per-tenant basis through a `values.yaml` file located in the tenant's overlay directory.

## Configuration Steps

To configure `oauth2-proxy` for a new tenant (e.g., `my-tenant`), follow these steps:

### 1. Locate the `values.yaml` File

The primary configuration file is located at:
`k8s/overlays/{tenant-name}/oauth2-values.yaml`

For example, for the `my-tenant` tenant, the file is at `k8s/overlays/my-tenant/oauth2-values.yaml`.

### 2. Configure OIDC Provider

In the `extraArgs` section of the `values.yaml`, set the `provider` and `client-id` for your OIDC provider (e.g., `google`, `github`).

```yaml
extraArgs:
  provider: google
  client-id: "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com"
  # ... other args
```

### 3. Manage Secrets Securely

**CRITICAL**: Do not hardcode secrets like `client-secret` or `cookie-secret` in the `values.yaml` file. These are managed through a dedicated Kubernetes secret.

The system is designed to automatically create a secret named `oauth2-proxy-secret` from a `.env` file.

**Action Required**:

1.  **Create or Edit the Secret File**: Open or create the file at `k8s/overlays/{tenant-name}/secrets/oauth2-proxy.env`.
2.  **Add Your Secrets**: Populate this file with the correct values for your OIDC application. The keys **must** be `OAUTH2_PROXY_CLIENT_SECRET` and `OAUTH2_PROXY_COOKIE_SECRET`.

    ```env
    # k8s/overlays/my-tenant/secrets/oauth2-proxy.env
    OAUTH2_PROXY_CLIENT_SECRET="YOUR_OIDC_CLIENT_SECRET"
    OAUTH2_PROXY_COOKIE_SECRET="A_VERY_STRONG_RANDOM_STRING_FOR_COOKIE_SECRET"
    ```

    To generate a strong cookie secret, you can use the following command:

    ```bash
    openssl rand -base64 32
    ```

3.  **Verify `kustomization.yaml`**: Ensure your tenant's `kustomization.yaml` contains the `secretGenerator` entry for `oauth2-proxy-secret`. This is typically already configured.

    ```yaml
    secretGenerator:
      - name: oauth2-proxy-secret
        envs:
          - secrets/oauth2-proxy.env
        options:
          disableNameSuffixHash: true
    ```

The Helm chart is configured to automatically detect and use these environment variables from the generated secret, so you can safely leave `client-secret` and `cookie-secret` out of your `values.yaml`.

### 4. Network Configuration (Ingress and Middlewares)

In addition to secrets and values, the tenant overlay configures how `oauth2-proxy` integrates with the Traefik Ingress controller. This is done via Kustomize patches.

-   **Ingress Patch:** A patch like `patches/oauth2-proxy-ingress-patch.yaml` sets the hostname for the `oauth2-proxy` service, exposing it to the internet.
-   **Middleware Patches:** Patches such as `patches/oauth2-proxy-authz-patch.yaml` configure Traefik `Middlewares`. These middlewares intercept requests to other applications and forward them to `oauth2-proxy` for authentication and authorization, effectively putting them behind a secure login.

This patching mechanism allows each tenant to define its own hostnames and fine-tune authentication flows without altering the base Helm chart configuration.

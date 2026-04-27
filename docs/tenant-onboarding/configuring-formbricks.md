# Configuring Formbricks for a New Tenant

Formbricks is a self-hosted survey and feedback platform. Its configuration is managed on a per-tenant basis, allowing each tenant to have its own instance with a custom domain and database.

## Prerequisites

-   A PostgreSQL instance must be available. You can use the shared [PostgreSQL component](../apps/postgres.md) or a dedicated one.
-   A database named `formbricks` must exist in the PostgreSQL instance.

## Configuration Steps

### 1. Enable the Component

Add the Formbricks component to your tenant's `kustomization.yaml`:

```yaml
resources:
  - ../../base
  - ../../components/apps/surveys/formbricks
  - ../../components/apps/databases/postgres  # if not already included
```

### 2. Provide Configuration (`formbricks-config.env`)

Copy the example from the component and customize it:

```bash
cp k8s/components/apps/surveys/formbricks/formbricks-config.env.example \
   k8s/overlays/{tenant-name}/configs/formbricks-config.env
```

Edit `k8s/overlays/{tenant-name}/configs/formbricks-config.env` with the tenant's values:

```env
NEXTAUTH_URL=https://surveys.your-domain.com
WEBAPP_URL=https://surveys.your-domain.com
PRIVACY_URL=https://surveys.your-domain.com/privacy
TERMS_URL=https://surveys.your-domain.com/terms
SIGNUP_DISABLED=0
EMAIL_VERIFICATION_DISABLED=1
INVITE_DISABLED=0
```

Add the `configMapGenerator` entry to your tenant's `kustomization.yaml`:

```yaml
configMapGenerator:
  - name: formbricks-config
    envs:
      - configs/formbricks-config.env
```

### 3. Provide Secrets (`formbricks-secret.env`)

Copy the example from the component and fill in the credentials:

```bash
cp k8s/components/apps/surveys/formbricks/formbricks-secret.env.example \
   k8s/overlays/{tenant-name}/secrets/formbricks-secret.env
```

Edit `k8s/overlays/{tenant-name}/secrets/formbricks-secret.env`:

```env
DATABASE_URL=postgresql://formbricks:your-password@postgres-service:5432/formbricks
NEXTAUTH_SECRET=generate-a-random-64-char-string
ENCRYPTION_KEY=generate-a-random-64-char-string
```

You can generate secure random strings with:

```bash
openssl rand -hex 32
```

Add the `secretGenerator` entry to your tenant's `kustomization.yaml`:

```yaml
secretGenerator:
  - name: formbricks-secret
    envs:
      - secrets/formbricks-secret.env
```

### 4. Patch the Ingress Hostname

Create the file `k8s/overlays/{tenant-name}/patches/formbricks-ingress-patch.yaml`:

```yaml
- op: replace
  path: /spec/rules/0/host
  value: surveys.your-domain.com
```

Add the patch to your `kustomization.yaml`:

```yaml
patches:
  - path: patches/formbricks-ingress-patch.yaml
    target:
      kind: Ingress
      name: formbricks-ingress
```

### 5. Optional: Configure TLS

If you want TLS termination at the Ingress level, add a TLS patch:

```yaml
- op: add
  path: /spec/tls
  value:
    - hosts:
        - surveys.your-domain.com
      secretName: tls-secret
```

## Validation

After configuring, validate the output with:

```bash
kubectl kustomize k8s/overlays/{tenant-name}
```

Verify that:
-   The `formbricks-ingress` has the correct hostname.
-   The `formbricks` Deployment has `envFrom` referencing `formbricks-config` and `formbricks-secret`.
-   The `ConfigMap` and `Secret` are generated from your `.env` files.

## How It Works

The Formbricks Deployment uses `envFrom` to inject all environment variables from two sources:
-   A `ConfigMap` (`formbricks-config`) for non-sensitive configuration like URLs and feature flags.
-   A `Secret` (`formbricks-secret`) for credentials like `DATABASE_URL`, `NEXTAUTH_SECRET`, and `ENCRYPTION_KEY`.

Both are created by the tenant's `kustomization.yaml` via `configMapGenerator` and `secretGenerator` from `.env` files. The `.env.example` files in the component serve as templates documenting the required keys.

# How to Contribute to the Forjate

This guide explains how to add new applications to the component catalog, making them available to be enabled in tenant overlays.

## Contribution Philosophy

The goal is to create a robust catalog of reusable components. When adding a new application, consider if it's a "local" component (managed within this repository) or a "remote" component (managed by an SME in an external repository).

---

## Pattern 1: Adding a Local Component

Use this pattern for components managed directly within this monorepo.

### Step 1: Create the Component Directory

1.  **Choose a Category**: Identify the correct category for your application under `k8s/components/apps/` (e.g., `databases`, `monitoring`). If a suitable category doesn't exist, create one.
2.  **Create the Directory**: Create a new directory for your app within that category.
    ```bash
    mkdir -p k8s/components/apps/new-category/my-new-app
    ```

### Step 2: Add Kubernetes Manifests

1.  **Add Manifests**: Place your generic Kubernetes manifest files (`deployment.yaml`, `service.yaml`, etc.) inside the new directory.
2.  **Use Placeholders**: Ensure that tenant-specific values like hostnames, domains, or image tags are either omitted or use placeholder values that can be easily patched by overlays. For Ingresses, a common practice is to use a placeholder hostname like `my-new-app.example.com`.

### Step 3: Create the Component's `kustomization.yaml`

Create a `kustomization.yaml` file in your component's directory that lists all its manifest files.

**Example: `k8s/components/apps/new-category/my-new-app/kustomization.yaml`**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - ingress.yaml
```

---

## Pattern 2: Adding a Remote Component

Use this pattern when an SME manages the component in their own Git repository. This factory will simply reference it.

### Step 1: Create the Component Stub

1.  **Choose a Category and Name**: Just like with a local component, create a directory for your component stub.
    ```bash
    mkdir -p k8s/components/apps/remote-apps/my-remote-app
    ```

### Step 2: Create the Remote `kustomization.yaml`

Create a `kustomization.yaml` file that points to the canonical source of the component in the external Git repository.

**Example: `k8s/components/apps/remote-apps/my-remote-app/kustomization.yaml`**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  # URL should point to the directory containing the kustomization file in the remote repo
  - https://github.com/sme-owner/my-remote-app.git/k8s/base?ref=v1.2.0
```
**Note**: It is best practice to pin the reference to a specific Git tag or commit hash (`?ref=...`) to ensure stable and predictable builds.

---

## Step 3: Enabling Your New Component for a Tenant

Once your component is in the catalog, any tenant can enable it:

1.  **Edit the Tenant Overlay**: Open the `kustomization.yaml` for the desired tenant (e.g., `k8s/overlays/my-tenant/kustomization.yaml`).
2.  **Add to Resources**: Add the path to your new component to the `resources` list.
    ```yaml
    resources:
      - ../../base
      # ... other resources
      - ../../components/apps/new-category/my-new-app
    ```
3.  **Add Patches**: If the component requires tenant-specific configuration (like a domain name), add a patch in the tenant's `patches/` directory and reference it in the `patches` section of the overlay's `kustomization.yaml`.

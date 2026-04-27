# Managing Reusable Components

Our platform is designed to be highly modular, using Kustomize to compose applications from various sources. These sources, which we call "components," can be either local to this repository or remote Git repositories.

## Local vs. Remote Components

-   **Local Components**: These are generic application manifests stored within this repository under `k8s/components/apps/`. They are suitable for simple, common applications or for components that are tightly coupled with the factory's logic.
-   **Remote Components**: These are Kustomize-compatible application manifests stored in their own dedicated Git repositories. This is the **recommended best practice** for any component that is developed and versioned independently, such as a tenant's own website or a shared microservice.

## Using a Remote Component

To use a remote component, you add it to the `resources` list in your tenant's `kustomization.yaml`.

### For Public Repositories

If the component's repository is public, you can use a standard HTTPS URL. You can also specify a sub-directory and a Git reference (like a branch, tag, or commit hash).

**Syntax**: `https://{host}/{org}/{repo}/{path-to-kustomize-dir}?ref={git-ref}`

**Example**:
```yaml
resources:
  - https://github.com/some-org/public-component/k8s/base?ref=v1.2.0
```

### For Private Repositories (Recommended)

To securely access private repositories without hardcoding credentials, use the SSH protocol. This leverages the SSH keys configured on the machine running the `kustomize build` command.

**Syntax**: `ssh://git@{host}/{org}/{repo}/{path-to-kustomize-dir}?ref={git-ref}`

**Example**:
```yaml
resources:
  - ssh://git@github.com/my-org/my-website.git/k8s/base?ref=main
```

## Customizing Components

The key advantage of this approach is that you can still customize any component—local or remote—using Kustomize `patches` from your tenant overlay.

For example, even if the `static-site` component is remote, you can have a local patch like `patches/static-site-ingress-patch.yaml` that modifies the hostname of its Ingress resource. Kustomize applies the local patch to the remote resource seamlessly.

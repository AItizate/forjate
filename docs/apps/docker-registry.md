# Docker Registry

**Official Documentation:** [https://docs.docker.com/registry/](https://docs.docker.com/registry/)

## Purpose in Architecture

The `Docker Registry` is a standard, open-source image registry for storing and distributing Docker images. Its role in our component catalog is to provide a **private, on-premise container registry**.

This is particularly useful for:
- Storing custom-built application images that should not be exposed on public registries like Docker Hub.
- Caching public images to reduce reliance on external services and improve build speeds.
- Enabling a fully air-gapped development and deployment workflow.

## Basic Operation

-   **Image Storage:** It provides a REST API for pushing and pulling Docker images (`docker push`, `docker pull`).
-   **Storage Backend:** The registry requires a storage backend to save the image layers. In our configuration, it uses a `PersistentVolumeClaim` to store data on a persistent volume within the cluster, typically provided by [Longhorn](./longhorn.md).
-   **Simple and Stateless:** The registry itself is a relatively simple, stateless application, with all the important data residing in the storage backend.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/docker-registry/`. It is not part of the `base` because not every tenant will require a private registry.
-   **Inclusion in Tenant:** To use the private registry, a tenant `overlay` must include this component in its `kustomization.yaml`.
-   **Exposure and Security:**
    -   It is exposed via an `Ingress` managed by [Traefik](./traefik.md). The hostname (e.g., `registry.tenant.com`) is configured in the overlay.
    -   **Important:** Securing a Docker registry is critical. The Ingress should be configured with TLS termination (`cert-manager`). For authentication, more advanced setups might involve a dedicated token-based auth service, but for simplicity, it can be protected at the Ingress level with [oauth2-proxy](./oauth2-proxy.md).
-   **Usage:** Once deployed and secured, developers can tag their images (`docker tag my-image registry.tenant.com/my-image`) and push them to the private registry. Kubernetes `Deployments` in the cluster can then pull images from this registry by setting the `image` field accordingly.

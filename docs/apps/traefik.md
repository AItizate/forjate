# Traefik Proxy

**Official Website:** [https://traefik.io/traefik/](https://traefik.io/traefik/)

## Purpose in Architecture

`Traefik` is a modern, **cloud-native Edge Router and Reverse Proxy**. In our Kubernetes cluster, it acts as the **Ingress Controller**. Its main function is to manage all incoming traffic from the outside to the services running inside the cluster.

It is the "front door" to all our applications.

## Basic Operation

-   **Automatic Service Discovery:** Traefik monitors the Kubernetes API in real-time. When an `Ingress` object is created, Traefik automatically detects it and creates the necessary routes to direct traffic to the correct service, without needing to restart or reload the configuration.
-   **Host/Path-Based Routing:** It directs incoming requests based on the hostname (e.g., `chat.example.com`) or path (e.g., `/api/v1`) specified in the `Ingress` rules.
-   **TLS Termination:** Traefik handles the HTTPS part of the connections. It uses the TLS certificates managed by [cert-manager](./cert-manager.md) to decrypt incoming traffic before passing it to the internal services.
-   **Middlewares:** One of its most powerful features is the `Middlewares` system. These are components that can process a request before it reaches the final service. In our project, we use `Middlewares` to:
    -   Integrate with [oauth2-proxy](./oauth2-proxy.md) for authentication (`ForwardAuth`).
    -   Add security headers.
    -   Handle HTTP to HTTPS redirections.

## Project Integration

-   **Base:** The base configuration for Traefik, including its `Deployment`, `ServiceAccount`, `ClusterRole`, and `ClusterRoleBinding` needed to access the Kubernetes API, is located in `k8s/base/apps/traefik/`.
-   **Entry Point:** It is deployed as a `Deployment` and exposed to the outside via a `Service` of type `LoadBalancer`. In a cloud environment, this would provision an external load balancer. In a bare-metal environment, it integrates with a solution like MetalLB.
-   **Route Definition:** The routes for each application are defined in `Ingress` objects within each application's configuration (e.g., `k8s/base/apps/open-webui/ingress.yaml`). These `Ingress` objects are generic in the `base` and are customized in the `overlays` with tenant-specific hostnames and TLS configurations.
-   **Security:** Traefik is the enforcement point for our perimeter security policy, forcing HTTPS and authentication through `oauth2-proxy`.

Traefik dramatically simplifies network routing management in Kubernetes, allowing for a declarative and dynamic configuration that perfectly fits our GitOps and Kustomize-based workflow.

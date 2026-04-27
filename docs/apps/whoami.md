# Whoami

**Official Image:** [https://hub.docker.com/r/traefik/whoami](https://hub.docker.com/r/traefik/whoami)

## Purpose in Architecture

`whoami` is a tiny web server that prints information about the HTTP request it receives. It's a simple yet invaluable **debugging and testing tool** for a Kubernetes environment.

Its primary purpose in our component catalog is to help diagnose and verify:
-   **Ingress Routing:** Is [Traefik](./traefik.md) correctly routing traffic for a specific hostname or path?
-   **Middleware Behavior:** Are middlewares (like `oauth2-proxy`) correctly forwarding headers to the backend service?
-   **Network Connectivity:** Is the pod reachable from the Ingress and other pods in the cluster?
-   **Source IPs:** What is the source IP address of the request as seen by the pod?

## Basic Operation

When you send an HTTP request to the `whoami` service, it responds with a plain text or JSON output that includes:
-   The hostname of the pod that served the request.
-   The IP address of the pod.
-   The headers from the incoming request.
-   The URL and method of the request.
-   The IP address of the client that made the request (as seen by the pod).

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/whoami/`.
-   **Inclusion in Tenant:** A tenant `overlay` can include this component to deploy a `whoami` instance for testing purposes. It is lightweight and not intended for production use.
-   **Usage Example:** To test if the `auth.tenant.com` Ingress and its `ForwardAuth` middleware are working, you could temporarily point the Ingress to the `whoami` service instead of the `oauth2-proxy` service. By inspecting the headers in the `whoami` output, you can see exactly what `oauth2-proxy` would have received, which is extremely useful for debugging authentication flows.

# Kubernetes Dashboard

**Official Repository:** [https://github.com/kubernetes/dashboard](https://github.com/kubernetes/dashboard)

## Purpose in Architecture

The `kubernetes-dashboard` is a general-purpose, web-based UI for Kubernetes clusters. It allows cluster administrators to manage applications running in the cluster and troubleshoot them, as well as manage the cluster itself.

In our project, it provides a "quick and dirty" graphical view of the cluster's state, useful for visual debugging or performing simple administrative tasks without extensive use of `kubectl`.

## Basic Operation

-   **Resource Visualization:** Displays most Kubernetes resources (Deployments, Pods, Services, etc.) and their current status.
-   **Basic Management:** Allows actions such as scaling a `Deployment`, restarting a `Pod`, or viewing its logs directly from the interface.
-   **Secure Access:** Access to the dashboard is protected. In our setup, it is exposed via an Ingress and secured by [oauth2-proxy](./oauth2-proxy.md) to ensure that only authorized users can access it.

## Project Integration

-   **Base:** The base configuration is located in `k8s/components/monitoring/kubernetes-dashboard/`.
-   **Service Account:** We create a `ServiceAccount` with read-only (`view`) permissions to limit the scope of what can be done from the dashboard by default. For administrative tasks, a `ServiceAccount` with more privileges would be required.
-   **Exposure:** The dashboard is exposed via [Traefik](./traefik.md) and secured with `oauth2-proxy`. The specific `Ingress` configuration is defined in each tenant's `overlay`, as the hostname (`dashboard.tenant.com`) is environment-specific.

It is a convenience tool for administration but is not critical to the functioning of the tenant's applications.

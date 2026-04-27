# MetalLB

**Official Website:** [https://metallb.universe.tf/](https://metallb.universe.tf/)

## Purpose in Architecture

`MetalLB` is a load-balancer implementation for bare metal Kubernetes clusters. It allows you to create Kubernetes services of type `LoadBalancer` in clusters that don't run on a cloud provider, and thus don't have a native load balancer solution.

Its role in our architecture is critical for **exposing services on bare metal or on-premise deployments**. It gives us the `LoadBalancer` functionality that is normally only available in cloud environments like GKE, EKS, or AKS.

## Basic Operation

MetalLB has two modes of operation:

1.  **Layer 2 Mode (ARP/NDP):**
    -   This is the simplest mode to configure.
    -   In this mode, one node in the cluster takes ownership of the service's external IP address. It uses standard address discovery protocols (ARP for IPv4, NDP for IPv6) to announce that IP on the local network.
    -   If the node that owns the IP fails, another node automatically takes over. This provides failover, but the network traffic is always directed to a single node at a time.

2.  **BGP Mode:**
    -   This is a more advanced and scalable mode.
    -   In BGP mode, MetalLB establishes a BGP peering session with a nearby router that you control. It then advertises the service's external IP to the router, allowing for true load balancing across multiple nodes.

## Project Integration

-   **Component:** The configuration is available as a component in `k8s/components/apps/networking/metallb/`.
-   **Inclusion in Tenant:** It is typically included in `overlays` that target bare metal or on-premise environments (e.g., `my-bare-metal`).
-   **Configuration:** The core of MetalLB's configuration is a `ConfigMap` where you define the `IPAddressPools` (the range of IP addresses the load balancer is allowed to use) and the peering configuration for BGP mode. This configuration is highly specific to the network environment and is managed in the `overlay`.
-   **Usage:** Once MetalLB is deployed and configured, any Kubernetes `Service` with `spec.type: LoadBalancer` will be assigned an external IP from the configured pool. This is how we expose services like the [Traefik](./traefik.md) Ingress Controller or the [Mosquitto](./mosquitto.md) MQTT broker to the local network.

# Node-RED

**Official Website:** [https://nodered.org/](https://nodered.org/)

## Purpose in Architecture

`Node-RED` is a flow-based programming tool, originally developed by IBM, for wiring together hardware devices, APIs, and online services in new and interesting ways. It provides a browser-based editor that makes it easy to wire together flows using a wide range of nodes in the palette.

In our component catalog, it serves as a powerful **low-code automation and integration platform**. It's ideal for:
-   Prototyping new services and integrations.
-   Creating custom automation workflows (e.g., "when a new file appears in Minio, send a notification").
-   Building simple dashboards and UIs.
-   Integrating with IoT devices and home automation systems.

## Basic Operation

-   **Flow-Based Editor:** The core of Node-RED is its visual editor. Users drag "nodes" from a palette onto a workspace and wire them together to create "flows."
-   **Nodes:** Each node has a well-defined purpose: it can inject messages, process them, or send them to an external service. There are nodes for HTTP requests, MQTT, databases, and thousands of other services.
-   **Message Passing:** Flows are triggered by messages. Each message is a simple JSON object that flows from one node to the next.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/node-red/`.
-   **Inclusion in Tenant:** A tenant `overlay` can include this component to deploy a Node-RED instance.
-   **Persistence:** Node-RED requires a persistent volume to store its flows, credentials, and any additional nodes installed by the user. This is handled by a `PersistentVolumeClaim`.
-   **Configuration:** A `ConfigMap` is used to manage the `settings.js` file, allowing for customization of the instance.
-   **Exposure and Security:** It is exposed via a [Traefik](./traefik.md) `Ingress` and should be protected by [oauth2-proxy](./oauth2-proxy.md) to ensure only authorized users can access the editor and build flows.

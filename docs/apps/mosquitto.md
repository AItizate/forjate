# Eclipse Mosquitto

**Official Website:** [https://mosquitto.org/](https://mosquitto.org/)

## Purpose in Architecture

`Eclipse Mosquitto` is a lightweight, open-source message broker that implements the MQTT (Message Queuing Telemetry Transport) protocol. MQTT is a standard messaging protocol for the Internet of Things (IoT), designed for low-bandwidth, high-latency, or unreliable networks.

In our component catalog, `Mosquitto` serves as the central **MQTT message bus**, primarily for the home automation stack but also for any general-purpose IoT or real-time messaging needs.

## Basic Operation

-   **Publish/Subscribe Model:** MQTT uses a pub/sub pattern.
    -   **Publishers** (like a temperature sensor) send messages to a "topic" (e.g., `home/livingroom/temperature`) without knowing who, if anyone, is listening.
    -   **Subscribers** (like Home Assistant or Node-RED) subscribe to topics they are interested in and receive all messages published to that topic.
    -   The **broker** (Mosquitto) is responsible for receiving all messages and forwarding them to the appropriate subscribers.
-   **Lightweight:** The protocol is designed to be simple and efficient, making it ideal for resource-constrained devices like ESP32s.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/brokers/mosquitto/`.
-   **Inclusion in Tenant:** A tenant `overlay` can deploy Mosquitto, typically as part of a home automation or IoT solution.
-   **Persistence:** It uses a `PersistentVolumeClaim` to store its data, including any retained messages and the security database.
-   **Configuration:** A `ConfigMap` can be used to mount a custom `mosquitto.conf` file to configure advanced features like user authentication, access control lists (ACLs), and TLS encryption.
-   **Exposure:** Mosquitto is typically not exposed outside the cluster via Ingress, as it doesn't use HTTP. Instead, its `Service` is exposed via a `LoadBalancer` or `NodePort` service to make the MQTT port (1883 for TCP, 8883 for TLS) accessible to devices on the local network.

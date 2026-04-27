# Home Assistant (Hass)

**Official Website:** [https://www.home-assistant.io/](https://www.home-assistant.io/)

## Purpose in Architecture

`Home Assistant` is a powerful open-source home automation platform that puts local control and privacy first. It acts as the central **brain of a smart home**, integrating with thousands of different devices and services.

Its role in our component catalog is to be the primary hub for any home automation deployments, orchestrating devices managed by [ESPHome](./esphome.md), scenes, and automations.

## Basic Operation

-   **Integrations:** Home Assistant's power comes from its vast library of integrations. It can talk to everything from Philips Hue lights and Tuya switches to weather services and MQTT brokers.
-   **Automations:** It has a powerful automation engine that allows you to define rules, such as "if the sun sets and someone is home, turn on the living room lights."
-   **Lovelace UI:** Provides a highly customizable web interface (called Lovelace) for controlling devices and viewing their status.
-   **Device Discovery:** It automatically scans the network to discover new devices, making setup easy.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/home-automation/hass/`.
-   **Inclusion in Tenant:** A tenant `overlay` can include this component to deploy a Home Assistant instance.
-   **Persistence:** This is critical. Home Assistant uses a `PersistentVolumeClaim` to store its entire configuration, including `configuration.yaml`, integrations, user data, and the history database. This must be backed by a reliable storage solution.
-   **Exposure and Security:** It is exposed via a [Traefik](./traefik.md) `Ingress` and must be protected by [oauth2-proxy](./oauth2-proxy.md).
-   **Networking:** For features like device auto-discovery to work correctly, the Home Assistant pod may need to run with `hostNetwork: true`. This is a privileged setting and is typically configured in the `overlay` via a patch, as it has security implications.

# ESPHome

**Official Website:** [https://esphome.io/](https://esphome.io/)

## Purpose in Architecture

`ESPHome` is a system to control your ESP8266/ESP32 boards by simple yet powerful configuration files and have them controlled remotely through Home Automation systems.

In our component catalog, `ESPHome` is a key part of the **home automation stack**. It allows users to:
-   Easily manage firmware for dozens of smart devices (sensors, switches, lights) from a central location.
-   Define device behavior using simple YAML files.
-   Integrate seamlessly with a central home automation hub, typically [Home Assistant](./hass.md).

## Basic Operation

-   **YAML Configuration:** You define a device's components (e.g., a Wi-Fi connection, a DHT22 temperature sensor, an MQTT client) in a YAML file.
-   **Firmware Compilation:** ESPHome takes this YAML file, converts it into C++ code, compiles it, and creates a firmware binary.
-   **Over-The-Air (OTA) Updates:** The compiled firmware can be flashed to devices over the network, making updates incredibly easy.
-   **Native API:** ESPHome devices use a highly-efficient native API to communicate with Home Assistant, providing real-time state updates.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/home-automation/esphome/`.
-   **Inclusion in Tenant:** A tenant `overlay` can include this component to deploy an `ESPHome` instance as part of a home automation solution.
-   **Persistence:** A `PersistentVolumeClaim` is used to store the YAML configurations for all devices, as well as the compiled firmware binaries.
-   **Exposure and Security:** It is exposed via a [Traefik](./traefik.md) `Ingress` and should be protected by [oauth2-proxy](./oauth2-proxy.md) to secure the dashboard.
-   **Integration with Home Assistant:** ESPHome is designed to work hand-in-hand with Home Assistant. Once a device is configured and on the network, Home Assistant will typically auto-discover it and allow you to add it as an integration.

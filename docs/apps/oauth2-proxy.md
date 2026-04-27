# oauth2-proxy

**Official Website:** [https://oauth2-proxy.github.io/oauth2-proxy/](https://oauth2-proxy.github.io/oauth2-proxy/)

## Purpose in Architecture

`oauth2-proxy` is a **reverse authentication proxy** that provides a security layer for web applications that do not have their own authentication and authorization system. Its function is to ensure that only users authenticated through an identity provider (IdP) such as Google, GitHub, Keycloak, etc., can access the internal services we expose.

It is the "security guard" of our web services.

## Basic Operation

`oauth2-proxy` sits between the user and the end application. The authentication flow, when integrated with [Traefik](./traefik.md), is as follows:

1.  **Initial Request:** A user tries to access a protected URL (e.g., `dashboard.example.com`).
2.  **Forward Authentication:** Traefik, through its `ForwardAuth` middleware, forwards the request to the `oauth2-proxy` service to verify if the user is authenticated.
3.  **Session Verification:** `oauth2-proxy` checks for a valid session cookie for that user.
    -   **If the session is valid**, it responds to Traefik with a `200 OK`, and Traefik allows the original request to proceed to the target application (e.g., `kubernetes-dashboard`).
    -   **If there is no session**, `oauth2-proxy` redirects the user to the login page of the configured identity provider (e.g., Google).
4.  **Login and Callback:** The user authenticates with the IdP. Once authenticated, the IdP redirects the user back to `oauth2-proxy` at a special callback URL.
5.  **Session Creation:** `oauth2-proxy` validates the IdP's response, optionally checks if the user belongs to an allowed organization or group, and if everything is correct, it creates an encrypted session cookie in the user's browser and redirects them to the original URL they wanted to visit.

## Project Integration

-   **Base:** The configuration is located in `k8s/base/apps/oauth2-proxy/`. It contains the necessary Traefik `Middlewares` for the `ForwardAuth` flow.
-   **Tenant-Specific Configuration:** The critical configuration (the `client-id`, `client-secret`, `cookie-secret`, and the list of allowed emails) is highly sensitive and environment-specific. It is managed in the `overlays` and injected into the `oauth2-proxy` `Deployment` via `Secrets`.
-   **Per-Application Activation:** To protect an application, that application's `Ingress` must include a reference to Traefik's `ForwardAuth` middleware in its `kustomization.yaml` within the `overlay`.

`oauth2-proxy` allows us to apply a consistent and robust authentication policy across all our exposed web applications, without the applications themselves needing to know how to do it.

> For more details on its configuration in a tenant, see the [oauth2-proxy Configuration Guide](../tenant-onboarding/configuring-oauth2-proxy.md).

# Formbricks

**Official Website:** [https://formbricks.com/](https://formbricks.com/)

## Purpose in Architecture

`Formbricks` is an open-source experience management platform for surveys, feedback collection, and user research. It enables tenants to create in-app surveys, link surveys, and website surveys to capture user feedback at every touchpoint.

Its role in our stack is to provide a **self-hosted, privacy-first survey and feedback solution** that integrates with existing applications without depending on third-party SaaS platforms.

## Basic Operation

-   **Survey Builder:** A visual editor for creating surveys with multiple question types (NPS, CES, open-ended, multiple choice, etc.).
-   **Multi-Channel Distribution:** Supports in-app surveys (via JavaScript SDK), link surveys (shareable URLs), and website pop-ups.
-   **Targeting and Triggers:** Surveys can be triggered based on user actions, page visits, or custom events within the application.
-   **Response Management:** Collects and aggregates responses with built-in analytics dashboards.
-   **API and Webhooks:** Exposes a REST API and webhook integrations for connecting survey data with other systems like [n8n](./n8n.md) or external analytics tools.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/surveys/formbricks/`.
-   **Inclusion in Tenant:** An `overlay` can deploy Formbricks by adding the component to its `resources`.
-   **Database Dependency:** Formbricks requires a PostgreSQL database. It can share an existing [PostgreSQL](./postgres.md) instance or use a dedicated one. The connection string is provided via a `Secret`.
-   **Configuration and Secrets:** The Deployment uses `envFrom` to inject all environment variables from two sources:
    -   A `ConfigMap` (`formbricks-config`) for non-sensitive settings like URLs and feature flags. The component includes a `formbricks-config.env.example` with the required keys.
    -   A `Secret` (`formbricks-secret`) for credentials: `DATABASE_URL`, `NEXTAUTH_SECRET`, and `ENCRYPTION_KEY`. The component includes a `formbricks-secret.env.example` as template.
    -   Both are provided by the tenant overlay via `configMapGenerator` and `secretGenerator`.
-   **Persistent Storage:** A `PersistentVolumeClaim` (5Gi default) is used for file uploads. This volume should be backed by a resilient storage solution like [Longhorn](./longhorn.md).
-   **Exposure:** Formbricks is exposed via a Traefik `Ingress`. The hostname in the base component uses a placeholder (`formbricks.example.com`) that must be patched by the tenant overlay.

> For details on enabling this component in a tenant, see the [Tenant Onboarding: Formbricks](../tenant-onboarding/configuring-formbricks.md) guide.

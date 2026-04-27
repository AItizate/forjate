# n8n

**Official Website:** [https://n8n.io/](https://n8n.io/)

## Purpose in Architecture

`n8n` is a free and source-available workflow automation tool. It enables you to connect any app with an API to any other, and manipulate their data with little or no code. It's a powerful alternative to services like Zapier or Make, but self-hosted.

In our component catalog, `n8n` serves as a more structured and robust **workflow automation engine** compared to the more free-form [Node-RED](./node-red.md). It is well-suited for:
-   Automating business processes.
-   Data synchronization between different applications (e.g., sync new GitHub issues to a Jira board).
-   Building custom API backends and webhooks.

## Basic Operation

-   **Node-Based Editor:** Similar to Node-RED, it uses a visual, node-based editor to build workflows.
-   **Nodes and Integrations:** It comes with a large library of pre-built nodes for hundreds of popular services (Google Sheets, Slack, Stripe, etc.).
-   **Triggers:** Workflows can be started by various triggers, such as a schedule (cron), a webhook call, or a manual execution.
-   **Data Flow:** Data passes between nodes in a structured way, making it easy to map fields from one service to another.

## Project Integration

-   **Component:** The configuration is available as a component in `k8s/components/apps/n8n/`.
-   **Database:** n8n requires a database to store credentials, workflows, and execution logs. The component includes a `PostgreSQL 15` database for this purpose, but it can be configured to use an external database. **PostgreSQL 13+ is required for n8n versions 1.50+**.
-   **Inclusion in Tenant:** An `overlay` can include this component to deploy an `n8n` instance. The overlay is responsible for providing the necessary secrets (like database credentials).
-   **Persistence:** Both the n8n application and its PostgreSQL database use `PersistentVolumeClaims` to ensure data is not lost.
-   **Exposure and Security:** It is exposed via a [Traefik](./traefik.md) `Ingress` and should be protected by [oauth2-proxy](./oauth2-proxy.md) to secure access to the editor.

## Version Compatibility

### n8n v1.50+ Requirements

For compatibility with recent n8n versions (1.50+), the following configurations are automatically applied:

- **PostgreSQL 15**: Required for optimal performance and feature support
- **Encryption Key**: Automatically configured for credential security
- **Binary Data Storage**: Configured for handling large files and data
- **Performance Tuning**: Optimized timeouts and resource management
- **Metrics**: Enabled for monitoring and diagnostics

### Environment Variables (Auto-configured)

- `N8N_ENCRYPTION_KEY`: 32-byte key for credential encryption (security critical)
- `N8N_BINARY_DATA_STORAGE_PATH`: Path for large file storage
- `N8N_WORKFLOW_TIMEOUT`: Maximum workflow execution time (300s)
- `N8N_METRICS_ENABLED`: Prometheus metrics collection
- `N8N_EXECUTIONS_DATA_PRUNE`: Automatic cleanup of old execution data
- `GENERIC_TIMEZONE`: Set to UTC for consistent scheduling

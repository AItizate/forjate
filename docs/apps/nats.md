# NATS

**Official Website:** [https://nats.io/](https://nats.io/)

## Purpose in Architecture

`NATS` is an **ultra-lightweight, high-performance messaging system** written in Go. In our ecosystem it serves as an alternative event bus for Change Data Capture (CDC) pipelines: it receives database change events from [Debezium](./debezium-mongo-nats.md) and makes them available to any interested service.

Compared to RabbitMQ, NATS has a significantly smaller resource footprint (~20MB RAM vs ~256MB), making it the preferred choice for tenants with resource constraints or for development environments where you still want event streaming capabilities.

## Basic Operation

-   **Core NATS:** A publish/subscribe model based on *subjects* (equivalent to topics or routing keys). Messages are fire-and-forget — if no subscriber is listening, the message is lost.
-   **JetStream:** NATS's persistence layer, enabled in this component. JetStream adds:
    -   **Streams:** Named append-only logs that persist messages to disk. Consumers can replay from any offset.
    -   **Consumers:** Stateful cursors over a stream. Supports push (server delivers) and pull (client fetches) models.
    -   **Retention policies:** Messages can be retained by time, size, or message count.
-   **Subject format (CDC):** When used alongside Debezium, subjects follow the pattern `{prefix}.{database}.{collection}` — for example `cdc.mydb.orders`. JetStream wildcards (`cdc.>`) can capture all CDC events in a single stream.
-   **Monitoring:** A lightweight HTTP endpoint on port `8222` exposes server stats, connection counts, and JetStream stream information.

## Project Integration

-   **Component path:** `k8s/components/apps/brokers/nats/`
-   **Image:** `nats:2.10-alpine` (~10MB image)
-   **Ports exposed via Service:**
    -   `4222` — Client connections (NATS protocol)
    -   `8222` — HTTP monitoring
    -   `6222` — Cluster routing (disabled by default; add a `cluster {}` block via patch for multi-node setups)
-   **JetStream storage:** Configured with `max_file_store: 5GB` on a `PersistentVolumeClaim` of 5Gi. Tenant overlays can patch both values.
-   **Authentication:** Simple username/password, resolved from `nats-secret` via environment variable substitution in `nats-server.conf`.

### Enabling for a Tenant

Add the component to the tenant overlay's `resources`:

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
```

Provide credentials via `secretGenerator` or `SealedSecret`:

```bash
# k8s/overlays/my-tenant/secrets/nats.env
NATS_USER=admin
NATS_PASS=supersecret
```

```yaml
secretGenerator:
  - name: nats-secret
    envs: [secrets/nats.env]
    options:
      disableNameSuffixHash: true
```

### Creating a JetStream Stream

Debezium publishes to NATS subjects and JetStream auto-creates streams if the server is configured to do so. For explicit control, create the stream manually after deployment using the NATS CLI:

```bash
# Install the NATS CLI
brew install nats-io/nats-tools/nats

# Port-forward
kubectl port-forward svc/nats 4222:4222 -n <namespace>

# Create a stream that captures all CDC events, retained for 7 days
nats stream add CDC_STREAM \
  --subjects "cdc.>" \
  --retention limits \
  --max-age 7d \
  --storage file \
  --server nats://admin:supersecret@localhost:4222
```

Consumers then create their own named subscription on the stream:

```bash
# Create a durable consumer for a specific service
nats consumer add CDC_STREAM orders-processor \
  --filter "cdc.mydb.orders" \
  --deliver all \
  --ack explicit \
  --server nats://admin:supersecret@localhost:4222
```

### Relationship with Debezium

NATS JetStream is the sink for the CDC pipeline. See [configuring-mongodb-cdc.md](../tenant-onboarding/configuring-mongodb-cdc.md) for the full setup guide.

# Debezium Server — PostgreSQL → NATS JetStream

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the PostgreSQL Write-Ahead Log (WAL) via logical replication and publishes every insert, update, and delete as a message to [NATS JetStream](./nats.md).

Its key value is that **no application code changes are required**. Any service writing to PostgreSQL automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

This component is functionally identical to [debezium-postgres-rabbitmq](./debezium-postgres-rabbitmq.md) — the only difference is the sink. Choose NATS when you prefer a lighter infrastructure footprint or when NATS is already present in the cluster.

## Basic Operation

1.  **Connects to PostgreSQL logical replication:** PostgreSQL exposes a real-time stream of all row-level changes via its WAL using the `pgoutput` logical decoding plugin (built-in since PostgreSQL 10). Debezium creates a replication slot and subscribes to this stream.
2.  **Transforms operations into events:** Each database operation (insert, update, delete) is serialized as a JSON payload containing the before/after state of the row, the operation type, and metadata (timestamp, schema, table).
3.  **Publishes to NATS JetStream:** The event is sent to a NATS subject following the pattern `{topic.prefix}.{schema}.{table}`, for example `cdc.public.orders`. JetStream persists these messages according to the stream's retention policy.
4.  **Persists its offset:** To survive restarts without reprocessing, Debezium stores its position in the WAL in a file backed by a `PersistentVolumeClaim`.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-postgres-nats/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (PostgreSQL credentials, NATS credentials) are injected as environment variables from a `Secret`.

### Prerequisites

-   **PostgreSQL must have `wal_level=logical`.**

    To check:
    ```sql
    SHOW wal_level;
    ```

    To enable:
    ```sql
    ALTER SYSTEM SET wal_level = 'logical';
    ```
    Then restart PostgreSQL.

-   **The connecting user must have `REPLICATION` privilege:**
    ```sql
    ALTER USER myuser REPLICATION;
    ```

-   **[NATS](./nats.md)** must be deployed and reachable from the same namespace (or patched with the correct URL).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-postgres-nats
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-postgres-nats.env
POSTGRES_HOST=postgres.default.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_USER=debezium
POSTGRES_PASSWORD=supersecret
POSTGRES_DB=mydb
NATS_USER=admin
NATS_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-postgres-nats-secret
    envs: [secrets/debezium-postgres-nats.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Tables

The default configuration watches `public.*` (all tables in the `public` schema). Patch the `ConfigMap` in your overlay to specify the exact tables:

```yaml
# k8s/overlays/my-tenant/patches/debezium-postgres-nats-tables-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-postgres-nats-config
data:
  application.properties: |
    debezium.sink.type=nats-jetstream
    debezium.sink.nats-jetstream.url=nats://nats.default.svc.cluster.local:4222
    debezium.sink.nats-jetstream.username=${NATS_USER}
    debezium.sink.nats-jetstream.password=${NATS_PASS}
    debezium.source.connector.class=io.debezium.connector.postgresql.PostgresConnector
    debezium.source.topic.prefix=cdc
    debezium.source.database.hostname=${POSTGRES_HOST}
    debezium.source.database.port=${POSTGRES_PORT}
    debezium.source.database.user=${POSTGRES_USER}
    debezium.source.database.password=${POSTGRES_PASSWORD}
    debezium.source.database.dbname=${POSTGRES_DB}
    debezium.source.plugin.name=pgoutput
    debezium.source.table.include.list=public.orders,public.users
    debezium.source.snapshot.mode=initial
    debezium.source.offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
    debezium.source.offset.storage.file.filename=/debezium/data/offsets.dat
    debezium.source.offset.flush.interval.ms=0
```

```yaml
# In kustomization.yaml patches section:
patches:
  - path: patches/debezium-postgres-nats-tables-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-postgres-nats-config
```

### Event Format

Each message published to NATS contains a JSON payload with the full row change:

```json
{
  "op": "c",
  "before": null,
  "after": { "id": 1, "name": "Alice", "amount": 100 },
  "source": {
    "schema": "public",
    "table": "orders",
    "db": "mydb",
    "ts_ms": 1700000000000
  }
}
```

Operation codes: `c` = create, `u` = update, `d` = delete, `r` = read (snapshot).

For a complete tenant setup walkthrough, see [configuring-cdc.md](../tenant-onboarding/configuring-cdc.md).

# Debezium Server — PostgreSQL → RabbitMQ

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the PostgreSQL Write-Ahead Log (WAL) via logical replication and publishes every insert, update, and delete as an AMQP message to [RabbitMQ](./rabbitmq.md).

Its key value is that **no application code changes are required**. Any service writing to PostgreSQL automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

## Basic Operation

1.  **Connects to PostgreSQL logical replication:** PostgreSQL exposes a real-time stream of all row-level changes via its WAL using the `pgoutput` logical decoding plugin (built-in since PostgreSQL 10). Debezium creates a replication slot and subscribes to this stream.
2.  **Transforms operations into events:** Each database operation (insert, update, delete) is serialized as a JSON payload containing the before/after state of the row, the operation type, and metadata (timestamp, schema, table).
3.  **Publishes to RabbitMQ:** The event is sent as an AMQP message to RabbitMQ. The routing key follows the pattern `{topic.prefix}.{schema}.{table}`, for example `cdc.public.orders`.
4.  **Persists its offset:** To survive restarts without reprocessing, Debezium stores its position in the WAL in a file backed by a `PersistentVolumeClaim`.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-postgres-rabbitmq/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (PostgreSQL credentials, RabbitMQ credentials) are injected as environment variables from a `Secret`.

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

-   **[RabbitMQ](./rabbitmq.md)** must be deployed and reachable from the same namespace (or patched with the correct hostname).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-postgres-rabbitmq
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-postgres-rabbitmq.env
POSTGRES_HOST=postgres.default.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_USER=debezium
POSTGRES_PASSWORD=supersecret
POSTGRES_DB=mydb
RABBITMQ_USER=admin
RABBITMQ_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-postgres-rabbitmq-secret
    envs: [secrets/debezium-postgres-rabbitmq.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Tables

The default configuration watches `public.*` (all tables in the `public` schema). Patch the `ConfigMap` in your overlay to specify the exact tables:

```yaml
# k8s/overlays/my-tenant/patches/debezium-postgres-rabbitmq-tables-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-postgres-rabbitmq-config
data:
  application.properties: |
    debezium.sink.type=rabbitmq
    debezium.sink.rabbitmq.connection.host=rabbitmq.default.svc.cluster.local
    debezium.sink.rabbitmq.connection.port=5672
    debezium.sink.rabbitmq.connection.username=${RABBITMQ_USER}
    debezium.sink.rabbitmq.connection.password=${RABBITMQ_PASS}
    debezium.sink.rabbitmq.connection.virtualHost=/
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
  - path: patches/debezium-postgres-rabbitmq-tables-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-postgres-rabbitmq-config
```

### Event Format

Each message published to RabbitMQ contains a JSON payload with the full row change:

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

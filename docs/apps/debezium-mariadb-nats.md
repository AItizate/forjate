# Debezium Server — MariaDB → NATS JetStream

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the MariaDB binary log (binlog) and publishes every insert, update, and delete as a message to [NATS JetStream](./nats.md).

Its key value is that **no application code changes are required**. Any service writing to MariaDB automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

This component is functionally identical to [debezium-mariadb-rabbitmq](./debezium-mariadb-rabbitmq.md) — the only difference is the sink. Choose NATS when you prefer a lighter infrastructure footprint or when NATS is already present in the cluster.

## Basic Operation

1.  **Connects to MariaDB binlog:** MariaDB records all row-level changes in its binary log. Debezium acts as a replication client and reads the binlog in real time.
2.  **Transforms operations into events:** Each database operation (insert, update, delete) is serialized as a JSON payload containing the before/after state of the row, the operation type, and metadata (timestamp, database, table).
3.  **Publishes to NATS JetStream:** The event is sent to a NATS subject following the pattern `{topic.prefix}.{database}.{table}`, for example `cdc.mydb.orders`. JetStream persists these messages according to the stream's retention policy.
4.  **Persists its offset and schema history:** To survive restarts without reprocessing, Debezium stores its binlog position in a file backed by a `PersistentVolumeClaim`. Additionally, unlike MongoDB and PostgreSQL, MariaDB's binlog does not contain table structure information, so Debezium maintains a separate **schema history** file to track DDL changes.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-mariadb-nats/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Schema history:** Stored at `/debezium/data/schema-history.dat` on the same PVC. Required for MariaDB — Debezium uses it to interpret binlog events correctly after schema changes (ALTER TABLE, etc.).
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (MariaDB credentials, NATS credentials) are injected as environment variables from a `Secret`.

### Prerequisites

-   **MariaDB must have binlog enabled with ROW format:**

    Check current settings:
    ```sql
    SHOW VARIABLES LIKE 'binlog_format';
    SHOW VARIABLES LIKE 'binlog_row_image';
    ```

    Required configuration in `my.cnf` / `mariadb.conf.d/`:
    ```ini
    [mysqld]
    log_bin           = mariadb-bin
    binlog_format     = ROW
    binlog_row_image  = FULL
    server_id         = 1
    ```

-   **The connecting user must have replication privileges:**
    ```sql
    GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'debezium'@'%';
    ```

-   **[NATS](./nats.md)** must be deployed and reachable from the same namespace (or patched with the correct URL).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-mariadb-nats
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-mariadb-nats.env
MARIADB_HOST=mariadb.default.svc.cluster.local
MARIADB_PORT=3306
MARIADB_USER=debezium
MARIADB_PASSWORD=supersecret
NATS_USER=admin
NATS_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-mariadb-nats-secret
    envs: [secrets/debezium-mariadb-nats.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Tables

The default configuration watches `mydb.*` (all tables in database `mydb`). Patch the `ConfigMap` in your overlay to specify the exact databases and tables:

```yaml
# k8s/overlays/my-tenant/patches/debezium-mariadb-nats-tables-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-mariadb-nats-config
data:
  application.properties: |
    debezium.sink.type=nats-jetstream
    debezium.sink.nats-jetstream.url=nats://nats.default.svc.cluster.local:4222
    debezium.sink.nats-jetstream.username=${NATS_USER}
    debezium.sink.nats-jetstream.password=${NATS_PASS}
    debezium.source.connector.class=io.debezium.connector.mariadb.MariaDbConnector
    debezium.source.topic.prefix=cdc
    debezium.source.database.hostname=${MARIADB_HOST}
    debezium.source.database.port=${MARIADB_PORT}
    debezium.source.database.user=${MARIADB_USER}
    debezium.source.database.password=${MARIADB_PASSWORD}
    debezium.source.database.server.id=1
    debezium.source.database.include.list=mydb
    debezium.source.table.include.list=mydb.orders,mydb.users
    debezium.source.snapshot.mode=initial
    debezium.source.offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
    debezium.source.offset.storage.file.filename=/debezium/data/offsets.dat
    debezium.source.offset.flush.interval.ms=0
    debezium.source.schema.history.internal=io.debezium.storage.file.history.FileSchemaHistory
    debezium.source.schema.history.internal.file.filename=/debezium/data/schema-history.dat
```

```yaml
# In kustomization.yaml patches section:
patches:
  - path: patches/debezium-mariadb-nats-tables-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-mariadb-nats-config
```

### Event Format

Each message published to NATS contains a JSON payload with the full row change:

```json
{
  "op": "c",
  "before": null,
  "after": { "id": 1, "name": "Alice", "amount": 100 },
  "source": {
    "table": "orders",
    "db": "mydb",
    "ts_ms": 1700000000000
  }
}
```

Operation codes: `c` = create, `u` = update, `d` = delete, `r` = read (snapshot).

For a complete tenant setup walkthrough, see [configuring-cdc.md](../tenant-onboarding/configuring-cdc.md).

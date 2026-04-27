# Debezium Server — MariaDB → RabbitMQ

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the MariaDB binary log (binlog) and publishes every insert, update, and delete as an AMQP message to [RabbitMQ](./rabbitmq.md).

Its key value is that **no application code changes are required**. Any service writing to MariaDB automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

## Basic Operation

1.  **Connects to MariaDB binlog:** MariaDB records all row-level changes in its binary log. Debezium acts as a replication client and reads the binlog in real time.
2.  **Transforms operations into events:** Each database operation (insert, update, delete) is serialized as a JSON payload containing the before/after state of the row, the operation type, and metadata (timestamp, database, table).
3.  **Publishes to RabbitMQ:** The event is sent as an AMQP message to RabbitMQ. The routing key follows the pattern `{topic.prefix}.{database}.{table}`, for example `cdc.mydb.orders`.
4.  **Persists its offset and schema history:** To survive restarts without reprocessing, Debezium stores its binlog position in a file backed by a `PersistentVolumeClaim`. Additionally, unlike MongoDB and PostgreSQL, MariaDB's binlog does not contain table structure information, so Debezium maintains a separate **schema history** file to track DDL changes.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-mariadb-rabbitmq/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Schema history:** Stored at `/debezium/data/schema-history.dat` on the same PVC. Required for MariaDB — Debezium uses it to interpret binlog events correctly after schema changes (ALTER TABLE, etc.).
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (MariaDB credentials, RabbitMQ credentials) are injected as environment variables from a `Secret`.

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

-   **[RabbitMQ](./rabbitmq.md)** must be deployed and reachable from the same namespace (or patched with the correct hostname).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-mariadb-rabbitmq
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-mariadb-rabbitmq.env
MARIADB_HOST=mariadb.default.svc.cluster.local
MARIADB_PORT=3306
MARIADB_USER=debezium
MARIADB_PASSWORD=supersecret
RABBITMQ_USER=admin
RABBITMQ_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-mariadb-rabbitmq-secret
    envs: [secrets/debezium-mariadb-rabbitmq.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Tables

The default configuration watches `mydb.*` (all tables in database `mydb`). Patch the `ConfigMap` in your overlay to specify the exact databases and tables:

```yaml
# k8s/overlays/my-tenant/patches/debezium-mariadb-rabbitmq-tables-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-mariadb-rabbitmq-config
data:
  application.properties: |
    debezium.sink.type=rabbitmq
    debezium.sink.rabbitmq.connection.host=rabbitmq.default.svc.cluster.local
    debezium.sink.rabbitmq.connection.port=5672
    debezium.sink.rabbitmq.connection.username=${RABBITMQ_USER}
    debezium.sink.rabbitmq.connection.password=${RABBITMQ_PASS}
    debezium.sink.rabbitmq.connection.virtualHost=/
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
  - path: patches/debezium-mariadb-rabbitmq-tables-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-mariadb-rabbitmq-config
```

### Event Format

Each message published to RabbitMQ contains a JSON payload with the full row change:

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

# Debezium Server — MongoDB → RabbitMQ

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the MongoDB operation log (oplog) via Change Streams and publishes every insert, update, and delete as an AMQP message to [RabbitMQ](./rabbitmq.md).

Its key value is that **no application code changes are required**. Any service writing to MongoDB automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

## Basic Operation

1.  **Connects to MongoDB Change Streams:** MongoDB exposes a real-time stream of all operations on collections. Debezium subscribes to this stream using MongoDB's native Change Streams API.
2.  **Transforms operations into events:** Each database operation (insert, update, replace, delete) is serialized as a JSON payload containing the before/after state of the document, the operation type, and metadata (timestamp, collection, namespace).
3.  **Publishes to RabbitMQ:** The event is sent as an AMQP message to RabbitMQ. The routing key follows the pattern `{topic.prefix}.{database}.{collection}`, for example `cdc.mydb.orders`.
4.  **Persists its offset:** To survive restarts without reprocessing, Debezium stores its position in the MongoDB oplog in a file backed by a `PersistentVolumeClaim`.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-mongo-rabbitmq/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (MongoDB URI, RabbitMQ credentials) are injected as environment variables from a `Secret`.

### Prerequisites

-   **MongoDB must run as a replica set**, even in a single-node setup. Change Streams are only available on replica sets.

    To initialize a single-node replica set:
    ```bash
    mongosh --eval 'rs.initiate()'
    ```

-   **[RabbitMQ](./rabbitmq.md)** must be deployed and reachable from the same namespace (or patched with the correct hostname).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-mongo-rabbitmq
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-mongo-rabbitmq.env
MONGODB_URI=mongodb://user:pass@mongodb.default.svc.cluster.local:27017/?replicaSet=rs0&authSource=admin
RABBITMQ_USER=admin
RABBITMQ_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-mongo-rabbitmq-secret
    envs: [secrets/debezium-mongo-rabbitmq.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Collections

The default configuration watches `mydb.*` (all collections in database `mydb`). Patch the `ConfigMap` in your overlay to specify the exact collections:

```yaml
# k8s/overlays/my-tenant/patches/debezium-mongo-rabbitmq-collections-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-mongo-rabbitmq-config
data:
  application.properties: |
    debezium.sink.type=rabbitmq
    debezium.sink.rabbitmq.connection.host=rabbitmq.default.svc.cluster.local
    debezium.sink.rabbitmq.connection.port=5672
    debezium.sink.rabbitmq.connection.username=${RABBITMQ_USER}
    debezium.sink.rabbitmq.connection.password=${RABBITMQ_PASS}
    debezium.sink.rabbitmq.connection.virtualHost=/
    debezium.source.connector.class=io.debezium.connector.mongodb.MongoDbConnector
    debezium.source.topic.prefix=cdc
    debezium.source.mongodb.connection.string=${MONGODB_URI}
    debezium.source.collection.include.list=mydb.orders,mydb.users
    debezium.source.snapshot.mode=initial
    debezium.source.offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
    debezium.source.offset.storage.file.filename=/debezium/data/offsets.dat
    debezium.source.offset.flush.interval.ms=0
```

```yaml
# In kustomization.yaml patches section:
patches:
  - path: patches/debezium-mongo-rabbitmq-collections-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-mongo-rabbitmq-config
```

### Event Format

Each message published to RabbitMQ contains a JSON payload with the full document change:

```json
{
  "op": "c",
  "after": { "_id": "...", "name": "Alice", "amount": 100 },
  "source": {
    "collection": "orders",
    "db": "mydb",
    "ts_ms": 1700000000000
  }
}
```

Operation codes: `c` = create, `u` = update, `d` = delete, `r` = read (snapshot).

For a complete tenant setup walkthrough, see [configuring-cdc.md](../tenant-onboarding/configuring-cdc.md).

# Debezium Server — MongoDB → NATS JetStream

**Official Website:** [https://debezium.io/](https://debezium.io/)

## Purpose in Architecture

`Debezium Server` is a **standalone Change Data Capture (CDC) engine** that reads the MongoDB operation log (oplog) via Change Streams and publishes every insert, update, and delete as a message to [NATS JetStream](./nats.md).

Its key value is that **no application code changes are required**. Any service writing to MongoDB automatically produces events that other services can consume, enabling event-driven architectures without touching existing code.

This component is functionally identical to [debezium-mongo-rabbitmq](./debezium-mongo-rabbitmq.md) — the only difference is the sink. Choose NATS when you prefer a lighter infrastructure footprint or when NATS is already present in the cluster.

## Basic Operation

1.  **Connects to MongoDB Change Streams:** MongoDB exposes a real-time stream of all operations on collections. Debezium subscribes to this stream using MongoDB's native Change Streams API.
2.  **Transforms operations into events:** Each database operation (insert, update, replace, delete) is serialized as a JSON payload containing the before/after state of the document, the operation type, and metadata (timestamp, collection, namespace).
3.  **Publishes to NATS JetStream:** The event is sent to a NATS subject following the pattern `{topic.prefix}.{database}.{collection}`, for example `cdc.mydb.orders`. JetStream persists these messages according to the stream's retention policy.
4.  **Persists its offset:** To survive restarts without reprocessing, Debezium stores its position in the MongoDB oplog in a file backed by a `PersistentVolumeClaim`.

## Project Integration

-   **Component path:** `k8s/components/apps/cdc/debezium-mongo-nats/`
-   **Image:** `quay.io/debezium/server:3.0` (standalone server, no Kafka Connect required)
-   **Replicas:** Always `1`. Multiple instances would produce duplicate events.
-   **Offset storage:** `PersistentVolumeClaim` of 1Gi at `/debezium/data/offsets.dat`. Deleting the PVC causes Debezium to re-snapshot from the beginning.
-   **Configuration:** `application.properties` mounted from a `ConfigMap`. Sensitive values (MongoDB URI, NATS credentials) are injected as environment variables from a `Secret`.

### Prerequisites

-   **MongoDB must run as a replica set**, even in a single-node setup. Change Streams are only available on replica sets.

    To initialize a single-node replica set:
    ```bash
    mongosh --eval 'rs.initiate()'
    ```

-   **[NATS](./nats.md)** must be deployed and reachable from the same namespace (or patched with the correct URL).

### Enabling for a Tenant

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-mongo-nats
```

Provide the required secret:

```bash
# k8s/overlays/my-tenant/secrets/debezium-mongo-nats.env
MONGODB_URI=mongodb://user:pass@mongodb.default.svc.cluster.local:27017/?replicaSet=rs0&authSource=admin
NATS_USER=admin
NATS_PASS=supersecret
```

```yaml
secretGenerator:
  - name: debezium-mongo-nats-secret
    envs: [secrets/debezium-mongo-nats.env]
    options:
      disableNameSuffixHash: true
```

### Patching the Watched Collections

The default configuration watches `mydb.*` (all collections in database `mydb`). Patch the `ConfigMap` in your overlay to specify the exact collections:

```yaml
# k8s/overlays/my-tenant/patches/debezium-mongo-nats-collections-patch.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: debezium-mongo-nats-config
data:
  application.properties: |
    debezium.sink.type=nats-jetstream
    debezium.sink.nats-jetstream.url=nats://nats.default.svc.cluster.local:4222
    debezium.sink.nats-jetstream.username=${NATS_USER}
    debezium.sink.nats-jetstream.password=${NATS_PASS}
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
  - path: patches/debezium-mongo-nats-collections-patch.yaml
    target:
      kind: ConfigMap
      name: debezium-mongo-nats-config
```

### Event Format

Each message published to NATS contains a JSON payload with the full document change:

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

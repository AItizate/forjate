# RabbitMQ

**Official Website:** [https://www.rabbitmq.com/](https://www.rabbitmq.com/)

## Purpose in Architecture

`RabbitMQ` is a **message broker** that enables asynchronous communication between services. In our ecosystem it serves as the event bus for Change Data Capture (CDC) pipelines: it receives database change events from [Debezium](./debezium-mongo-rabbitmq.md) and makes them available to any consumer interested in reacting to those changes.

Its role is to **decouple** the database (the source of truth) from the services that need to act on changes, without requiring any modification to the application that writes to the database.

## Basic Operation

-   **AMQP Protocol:** RabbitMQ speaks AMQP (Advanced Message Queuing Protocol), a mature and widely supported standard. Any client with an AMQP library (Java, Python, Node.js, Go, etc.) can connect to it.
-   **Exchanges and Queues:** Producers publish messages to an *exchange*. The exchange routes messages to *queues* based on routing keys. Consumers subscribe to queues.
-   **Routing key format (CDC):** When used alongside Debezium, the routing key follows the pattern `{prefix}.{database}.{collection}` — for example `cdc.mydb.orders`.
-   **Stream Queues:** Since RabbitMQ 3.9, *Stream Queues* provide an append-only log with persistent storage and replay from any offset. This means a new consumer can process all historical events without the producer needing to resend them, similar to Kafka topics.
-   **Management UI:** Available on port `15672`. Provides a visual interface for inspecting queues, exchanges, message rates, and consumer states.

## Project Integration

-   **Component path:** `k8s/components/apps/brokers/rabbitmq/`
-   **Plugins enabled:** `rabbitmq_management`, `rabbitmq_stream`, `rabbitmq_stream_management`
-   **Ports exposed via Service:**
    -   `5672` — AMQP (clients)
    -   `15672` — Management UI
    -   `5552` — RabbitMQ Stream protocol
-   **Storage:** A `PersistentVolumeClaim` of 5Gi backs the `StatefulSet`. Tenant overlays can patch the storage size or storage class.

### Enabling for a Tenant

Add the component to the tenant overlay's `resources`:

```yaml
# k8s/overlays/my-tenant/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
```

Provide credentials via `secretGenerator` or `SealedSecret`:

```bash
# k8s/overlays/my-tenant/secrets/rabbitmq.env
RABBITMQ_DEFAULT_USER=admin
RABBITMQ_DEFAULT_PASS=supersecret
```

```yaml
secretGenerator:
  - name: rabbitmq-secret
    envs: [secrets/rabbitmq.env]
    options:
      disableNameSuffixHash: true
```

### Setting Up Stream Queues

After the first deployment, create a stream queue bound to the CDC routing key pattern. This can be done via the Management UI or with `rabbitmqadmin`:

```bash
# Port-forward the management port
kubectl port-forward svc/rabbitmq 15672:15672 -n <namespace>

# Create a stream queue (via rabbitmqadmin or Management UI)
rabbitmqadmin declare queue name=cdc.mydb.orders durable=true arguments='{"x-queue-type":"stream"}'
```

> [!NOTE]
> Stream queues require consumers to specify from which offset they want to start consuming. On first connection, use `x-stream-offset: first` to read from the beginning or `x-stream-offset: next` to only receive new messages.

### Relationship with Debezium

RabbitMQ is the sink for the CDC pipeline. See [configuring-mongodb-cdc.md](../tenant-onboarding/configuring-mongodb-cdc.md) for the full setup guide.

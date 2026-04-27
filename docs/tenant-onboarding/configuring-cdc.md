# Configuring CDC (Change Data Capture)

This guide explains how to activate a CDC pipeline in a tenant overlay. The pipeline captures every write operation on database tables/collections and publishes them as events to a message bus, without requiring any changes to the application code.

## Overview

```
Database (MongoDB / PostgreSQL / MariaDB)
  └─→ Debezium Server (reads change stream / WAL / binlog)
        └─→ RabbitMQ  OR  NATS JetStream
              └─→ Your services (consumers)
```

Event subject/routing key format: `cdc.{database}.{table-or-collection}`
Examples: `cdc.mydb.orders`, `cdc.public.users`

## Available Components

| Source | Sink | Component path | CDC mechanism |
|--------|------|----------------|---------------|
| MongoDB | NATS | `cdc/debezium-mongo-nats` | Change Streams (oplog) |
| MongoDB | RabbitMQ | `cdc/debezium-mongo-rabbitmq` | Change Streams (oplog) |
| PostgreSQL | NATS | `cdc/debezium-postgres-nats` | Logical Replication (WAL) |
| PostgreSQL | RabbitMQ | `cdc/debezium-postgres-rabbitmq` | Logical Replication (WAL) |
| MariaDB | NATS | `cdc/debezium-mariadb-nats` | Binary Log (binlog) |
| MariaDB | RabbitMQ | `cdc/debezium-mariadb-rabbitmq` | Binary Log (binlog) |

All components use the same image (`quay.io/debezium/server:3.0`) and share the same deployment pattern: single replica, Recreate strategy, PVC-backed offset storage.

## Choose a Bus

| | RabbitMQ | NATS JetStream |
|---|---|---|
| **Component** | `brokers/rabbitmq` | `brokers/nats` |
| **RAM (broker)** | ~256Mi | ~64Mi |
| **Replay** | Yes (Stream Queues) | Yes (JetStream) |
| **Use when** | You already know RabbitMQ or need AMQP clients | You want a lighter footprint |

Both options are functionally equivalent for CDC. Pick one and follow the corresponding database section below.

---

## MongoDB CDC

### Step 1 — Ensure MongoDB runs as a Replica Set

Change Streams (required by Debezium) are only available when MongoDB runs as a replica set. This applies even to single-node deployments.

**Check if already initialized:**
```bash
mongosh --eval 'rs.status()'
```

**Initialize a single-node replica set (if not done):**
```bash
mongosh --eval 'rs.initiate()'
```

#### Using the factory's `replica-set` Component

The `k8s/components/apps/databases/mongodb/replica-set` Component handles RS initialization automatically. It adds `--replSet rs0`, a keyFile for intra-RS auth, and an idempotent init Job.

**Required: create the keyFile Secret before deploying**

MongoDB requires a shared keyFile when running with authentication (`MONGO_INITDB_ROOT_*` env vars) and `--replSet`. Generate and seal it once per namespace:

```bash
# Generate a random 512-byte keyFile
openssl rand -base64 512 | tr -d '\n' > keyfile

# Seal it (remote tenants using SealedSecrets)
kubectl create secret generic mongodb-keyfile \
  --from-file=keyfile=keyfile \
  -n <namespace> \
  --dry-run=client -o yaml \
  | kubeseal --scope cluster-wide -w secrets/sealed-mongodb-keyfile.yaml

rm keyfile  # remove the plaintext file
```

Add it to your `kustomization.yaml`:
```yaml
resources:
  - secrets/sealed-mongodb-keyfile.yaml
```

### Step 2 — Add CDC components

**With RabbitMQ:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-mongo-rabbitmq
```

**With NATS:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-mongo-nats
```

### Step 3 — Provide secrets

**RabbitMQ variant:**
```bash
# secrets/debezium-mongo-rabbitmq.env
MONGODB_URI=mongodb://user:pass@mongodb.default.svc.cluster.local:27017/?replicaSet=rs0&authSource=admin
RABBITMQ_USER=admin
RABBITMQ_PASS=change-me
```

**NATS variant:**
```bash
# secrets/debezium-mongo-nats.env
MONGODB_URI=mongodb://user:pass@mongodb.default.svc.cluster.local:27017/?replicaSet=rs0&authSource=admin
NATS_USER=admin
NATS_PASS=change-me
```

### Step 4 — Patch watched collections (optional)

Default watches `mydb.*`. See [debezium-mongo-nats](../apps/debezium-mongo-nats.md) or [debezium-mongo-rabbitmq](../apps/debezium-mongo-rabbitmq.md) for patching examples.

---

## PostgreSQL CDC

### Step 1 — Enable logical replication

PostgreSQL CDC uses the Write-Ahead Log (WAL) via the `pgoutput` logical decoding plugin (built-in since PostgreSQL 10).

**Check current WAL level:**
```sql
SHOW wal_level;
```

**Enable logical replication (requires restart):**
```sql
ALTER SYSTEM SET wal_level = 'logical';
```
Then restart PostgreSQL.

**Grant replication privilege to the Debezium user:**
```sql
CREATE USER debezium WITH REPLICATION PASSWORD 'supersecret';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
```

### Step 2 — Add CDC components

**With RabbitMQ:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-postgres-rabbitmq
```

**With NATS:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-postgres-nats
```

### Step 3 — Provide secrets

**RabbitMQ variant:**
```bash
# secrets/debezium-postgres-rabbitmq.env
POSTGRES_HOST=postgres.default.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_USER=debezium
POSTGRES_PASSWORD=supersecret
POSTGRES_DB=mydb
RABBITMQ_USER=admin
RABBITMQ_PASS=change-me
```

**NATS variant:**
```bash
# secrets/debezium-postgres-nats.env
POSTGRES_HOST=postgres.default.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_USER=debezium
POSTGRES_PASSWORD=supersecret
POSTGRES_DB=mydb
NATS_USER=admin
NATS_PASS=change-me
```

### Step 4 — Patch watched tables (optional)

Default watches `public.*`. See [debezium-postgres-nats](../apps/debezium-postgres-nats.md) or [debezium-postgres-rabbitmq](../apps/debezium-postgres-rabbitmq.md) for patching examples.

---

## MariaDB CDC

### Step 1 — Enable binlog with ROW format

MariaDB CDC reads the binary log. The binlog must be enabled and configured for row-level replication.

**Check current settings:**
```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'log_bin';
```

**Required configuration in `my.cnf` / `mariadb.conf.d/`:**
```ini
[mysqld]
log_bin           = mariadb-bin
binlog_format     = ROW
binlog_row_image  = FULL
server_id         = 1
```

Restart MariaDB after changing these settings.

**Grant replication privileges to the Debezium user:**
```sql
CREATE USER 'debezium'@'%' IDENTIFIED BY 'supersecret';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'debezium'@'%';
GRANT SELECT ON mydb.* TO 'debezium'@'%';
```

### Step 2 — Add CDC components

**With RabbitMQ:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/rabbitmq
  - ../../components/apps/cdc/debezium-mariadb-rabbitmq
```

**With NATS:**
```yaml
resources:
  - ../../base
  - ../../components/apps/brokers/nats
  - ../../components/apps/cdc/debezium-mariadb-nats
```

### Step 3 — Provide secrets

**RabbitMQ variant:**
```bash
# secrets/debezium-mariadb-rabbitmq.env
MARIADB_HOST=mariadb.default.svc.cluster.local
MARIADB_PORT=3306
MARIADB_USER=debezium
MARIADB_PASSWORD=supersecret
RABBITMQ_USER=admin
RABBITMQ_PASS=change-me
```

**NATS variant:**
```bash
# secrets/debezium-mariadb-nats.env
MARIADB_HOST=mariadb.default.svc.cluster.local
MARIADB_PORT=3306
MARIADB_USER=debezium
MARIADB_PASSWORD=supersecret
NATS_USER=admin
NATS_PASS=change-me
```

### Step 4 — Patch watched tables (optional)

Default watches `mydb.*`. Note that MariaDB requires **both** `database.include.list` and `table.include.list`. See [debezium-mariadb-nats](../apps/debezium-mariadb-nats.md) or [debezium-mariadb-rabbitmq](../apps/debezium-mariadb-rabbitmq.md) for patching examples.

### MariaDB-specific: Schema History

Unlike MongoDB and PostgreSQL, the MariaDB connector maintains a **schema history** file (`/debezium/data/schema-history.dat`) on the same PVC. This file tracks DDL changes (CREATE TABLE, ALTER TABLE, etc.) so Debezium can correctly interpret binlog events. **Do not delete the PVC** without understanding that both offsets and schema history will be lost, triggering a full re-snapshot.

---

## Verifying the Pipeline

### Check Debezium logs

```bash
# Replace <variant> with the component name, e.g.: debezium-postgres-nats
kubectl logs deployment/<variant> -n <namespace> -f
```

Look for: `Started DebbeziumServer` and the initial snapshot log lines.

### Trigger a test event

**MongoDB:**
```bash
mongosh --eval 'db.orders.insertOne({ item: "test", qty: 1 })'
```

**PostgreSQL:**
```sql
INSERT INTO orders (name, amount) VALUES ('test', 1);
```

**MariaDB:**
```sql
INSERT INTO orders (name, amount) VALUES ('test', 1);
```

### Consume the event

**RabbitMQ:**
```bash
# Via Management UI → Queues → cdc.mydb.orders → Get Messages
```

**NATS:**
```bash
nats sub "cdc.mydb.orders" --server nats://admin:change-me@localhost:4222
```

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `MongoCommandException: not primary` | MongoDB not in replica set mode | Run `rs.initiate()` |
| `mongod` refuses to start after adding `--replSet` | Missing keyFile when auth is enabled | Create the `mongodb-keyfile` Secret (see MongoDB Step 1) |
| `FATAL: number of requested standby connections exceeds max_wal_senders` | Too many replication slots | Increase `max_wal_senders` in postgresql.conf |
| `ERROR: logical decoding requires wal_level >= logical` | WAL level not set | `ALTER SYSTEM SET wal_level = 'logical'` and restart |
| `Access denied; you need REPLICATION SLAVE privilege` | MariaDB user lacks privileges | Grant `REPLICATION SLAVE, REPLICATION CLIENT` |
| `binlog_row_image is not FULL` | MariaDB binlog misconfigured | Set `binlog_row_image=FULL` and restart |
| JetStream unavailable / no meta-leader in NATS | Bare `cluster {}` block without `cluster.name` | Upgrade to factory `v1.7.1` which removes the block for single-node |
| Debezium pod restarts in loop | Cannot reach database or bus | Check service names and secrets |
| No events after insert | Table/collection not in include list | Patch the ConfigMap and restart the pod |
| Offsets lost after pod restart | No PVC bound | Check PVC is in `Bound` state |
| Duplicate events after pod restart | PVC deleted accidentally | PVC must persist across restarts |
| Schema history corrupted (MariaDB only) | PVC deleted mid-operation | Delete PVC and let Debezium re-snapshot |

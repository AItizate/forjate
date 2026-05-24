# `cdc-event-sourcing`

CDC pipeline: MongoDB (replica set) → Debezium → RabbitMQ. Ships with a post-deploy validation Job.

Full design in [`docs/overlays/cdc-event-sourcing.md`](../../../docs/overlays/cdc-event-sourcing.md).

## Before deploying

Copy each `.env.example` under `secrets/` and `namespaces/event-sourcing/secrets/` to the corresponding `.env` and fill in real values.

The `mongodb-keyfile` under `namespaces/event-sourcing/secrets/` is required for the Mongo replica-set's internal auth — generate one with:

```bash
openssl rand -base64 756 > namespaces/event-sourcing/secrets/mongodb-keyfile
chmod 400 namespaces/event-sourcing/secrets/mongodb-keyfile
```

## Build & deploy

```bash
kubectl kustomize k8s/overlays/cdc-event-sourcing | kubectl apply -f -
```

## Validate the pipeline

After apply, the `cdc-validate` Job runs once. Read its logs:

```bash
kubectl -n event-sourcing logs job/cdc-validate -f
```

`[PASS]` count should equal the test count; any `[FAIL]` line points at the broken step.

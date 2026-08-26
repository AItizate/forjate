# Use case: `db-migration-a-to-b`

> A source and a target database, side by side, for agents that move data between them.

An ephemeral environment: brought up on demand, seeded, validated, and thrown
away. It declares itself in [`usecase.yaml`](./usecase.yaml); the generic
runner does the rest.

**This is the reference scaffold for the ephemeral use-case pattern.** The
environment is real — Postgres and MongoDB from the component catalog, wired
up, credentialed, and validated. The migration itself is deliberately a stub:
what this proves is the lifecycle, not any particular ETL.

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up db-migration-a-to-b       # up, seeded, validated
./scripts/ephemeral/ephemeral.sh validate db-migration-a-to-b # re-run just the checks
./scripts/ephemeral/ephemeral.sh down db-migration-a-to-b     # tear it down
```

`up` blocks until the validate Job exits 0, so a zero exit status means both
databases are running and reachable at the advertised endpoints.

## What it runs

| Phase | Job | What it does |
|-------|-----|--------------|
| seed | `dbmig-seed` | Waits for Postgres to accept connections. **Fixtures are a TODO.** |
| run | `dbmig-migrate` | **Stub.** The mechanism-agnostic slot — a Python ETL Job, or an Airbyte connector once that component exists. |
| verify | `dbmig-validate` | Real: asserts Postgres accepts the contract's credentials and MongoDB is listening. |

## What it exposes

| Role | Address | Credentials |
|------|---------|-------------|
| source | `postgres.uc-db-migration-a-to-b.svc.cluster.local:5432` | Secret `postgres-secret` |
| target | `mongodb.uc-db-migration-a-to-b.svc.cluster.local:27017` | Secret `mongodb-secret` |

Declared in `spec.outputs` — an agent reads that rather than probing. The
runner prints the resolved endpoints when `up` completes.

Credentials come from `secrets/*.env`, which are gitignored and seeded from
their committed `.env.example` siblings. They are placeholder values for a
throwaway local environment and are not secrets in any meaningful sense.

## Isolation

`shared`, TTL `4h`. Two databases and three Jobs, nothing cluster-scoped — a
namespace on the reusable cluster is enough. See
[the design doc](../../../../docs/ephemeral-use-cases.md) for when a use case
needs `dedicated` instead.

## Turning this into a working reference

1. Fill `dbmig-seed` with a deterministic synthetic dataset and record row
   counts and a checksum in a manifest table.
2. Fill `dbmig-migrate` with a real migration.
3. Extend `dbmig-validate` to compare the manifest against what landed in
   MongoDB.

None of that touches `usecase.yaml`, the runner, or CI.

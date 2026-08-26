# Ephemeral use-case runner

Tooling for the ephemeral use-case environments described in
[`docs/ephemeral-use-cases.md`](../../docs/ephemeral-use-cases.md). Read that
first for the architecture; this page is the operator reference.

```
ephemeral.sh          up | seed | validate | down | ls | gc
create-usecase.sh     scaffold a new use case from templates
usecase.schema.json   the contract, formalized
lib/                  log, deps, cluster, usecase, job
```

## Requirements

`k3d`, `kubectl`, `yq` (v4, mikefarah), `docker`. `kustomize` is used when
present; otherwise the runner falls back to `kubectl kustomize`. Missing
dependencies are reported with install hints on first run.

## Commands

| Command | What it does |
|---------|--------------|
| `up <use-case>` | Ensure the cluster, apply the overlay, stamp the TTL, then run seed → run → verify. Blocks until verify exits 0. Idempotent. |
| `seed <use-case>` | Re-run only the seed Job against a live environment. |
| `validate <use-case>` | Re-run only the verify Job. |
| `down <use-case>` | Delete the namespace (shared) or the whole cluster (dedicated). |
| `ls` | Live environments with time remaining. |
| `gc [--dry-run]` | Reclaim everything past its TTL. |

```bash
./scripts/ephemeral/ephemeral.sh up db-migration-a-to-b
./scripts/ephemeral/ephemeral.sh ls
./scripts/ephemeral/ephemeral.sh down db-migration-a-to-b
```

Environment overrides: `K3D_IMAGE` (default `rancher/k3s:v1.31.3-k3s1`),
`UC_SHARED_CLUSTER` (default `forjate-uc-shared`).

## The contract

Every use case ships a `usecase.yaml`. It is what makes an environment
consumable by an agent instead of only by a person who read the README.

```yaml
apiVersion: forjate.io/v0
kind: UseCase
metadata:
  name: db-migration-a-to-b        # must equal the directory name
spec:
  isolation: shared                # shared | dedicated
  ttl: 4h                          # <N>m | <N>h | <N>d
  components:                      # informational inventory
    - apps/databases/postgres
  jobs:                            # executed in order; run is optional
    seed:   { name: dbmig-seed,     timeout: 300 }
    run:    { name: dbmig-migrate,  timeout: 600 }
    verify: { name: dbmig-validate, timeout: 300 }
  outputs:
    endpoints:
      - { name: source, service: postgres, port: 5432, protocol: postgresql }
    secrets:
      - { name: source-credentials, secretRef: postgres-secret,
          keys: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD] }
```

Validated against [`usecase.schema.json`](./usecase.schema.json) in CI, which
also asserts that `metadata.name` matches the directory and that every Job
named under `spec.jobs` exists in the built manifest.

**Resolving an endpoint.** Never guess or probe — apply the rule:

```
<service>.uc-<use-case-name>.svc.cluster.local:<port>
```

`up` prints the resolved endpoints when it finishes.

## Isolation

`shared` puts the use case in namespace `uc-<name>` on a single reusable
cluster (`forjate-uc-shared`). `dedicated` gives it a cluster of its own
(`forjate-uc-<name>`). Same overlay either way — only the contract changes.

**Declare `dedicated` when the use case installs CRDs, operators or
StorageClasses.** Those are cluster-scoped and survive namespace deletion, so
on a shared cluster they accumulate as residue for the next use case to trip
over.

There is no state file: namespace annotations (`forjate.io/expires-at`) and
k3d cluster metadata are the source of truth, so `ls` and `gc` stay correct
across restarts and branch switches. The shared cluster itself is never
garbage-collected — only the namespaces inside it expire.

## Why the Jobs ship suspended

Lifecycle Jobs carry `spec.suspend: true`. Applying the overlay creates them
without starting them, which is what lets the runner impose an order instead
of having all three race each other. `run_job` un-suspends one at a time,
deleting any previous run first because Jobs are immutable.

The manifest each Job runs from is extracted out of the built overlay, not
read from a file — what CI validates is exactly what executes.

## Adding a use case

```bash
./scripts/ephemeral/create-usecase.sh --name my-use-case --ttl 2h
```

Then:

1. Add the catalog components to
   `k8s/overlays/usecases/<name>/namespaces/uc-<name>/kustomization.yaml`
   (relative path: `../../../../../components/apps/<category>/<name>`).
2. Add a `secretGenerator` entry per component and commit a matching
   `secrets/<component>.env.example` — CI seeds the real `.env` from it, and
   so does the runner.
3. Fill the seed / run / verify Jobs and complete `spec.outputs`.
4. `./scripts/ephemeral/ephemeral.sh up <name>`.

The conventions a use case must satisfy are listed in
[`docs/overlays/CONVENTION.md`](../../docs/overlays/CONVENTION.md).

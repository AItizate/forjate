# Ephemeral use-case environments

An AI agent can write the code for a use case. It cannot conjure the Postgres, the broker, and the seeded dataset that use case needs to actually run.

This page describes how Forjate turns **a use case into a disposable environment**: declared as an overlay, spun up on a local cluster, seeded, validated end-to-end, and thrown away — with a machine-readable contract that tells an agent exactly what it got.

## The situation

Building a library of agent-driven use cases — "migrate a database from A to B", "ingest documents into a vector store", "route events through a broker into a workflow engine" — means every use case needs infrastructure to prove itself against.

The obvious move is a `docker-compose.yml` per use case, plus a couple of init and seed scripts. It works on day one. By use case number five it has three problems:

- **Nothing is shared.** Every use case re-declares its own Postgres, its own network, its own volumes. Forjate has a catalog of 40+ components and none of it is reachable from a compose file.
- **It isn't the real thing.** The agent is validated against a stack that resembles production instead of the manifests that *are* production. What passes in compose can still fail on the cluster.
- **The agent is flying blind.** "Is the database up yet? What's the connection string? Did the seed finish?" — a compose file answers none of that. Something has to poll, guess, or hard-code.

The overlay convention already solves most of this for tenants. A use case is just an overlay with a shorter life expectancy.

## The idea in one paragraph

**A use case is an overlay under `k8s/overlays/usecases/<name>/` that ships a contract (`usecase.yaml`), a seed Job, and a verify Job.** A generic runner reads the contract, brings up a k3d cluster (shared or dedicated), applies the overlay, runs seed → run → verify in order, and blocks until the verify Job exits 0. When it returns, the environment is provably ready and the contract tells you — or your agent — where everything is. A TTL stamped at creation time means forgetting to tear it down is not a leak.

_Diagram pending — the prompt that generates it lives at [`assets/architecture/ephemeral-usecases.prompt.md`](./assets/architecture/ephemeral-usecases.prompt.md)._

## The contract: `usecase.yaml`

This is the part that makes the pattern useful to agents rather than just convenient for humans. Every use case declares what it is and what it exposes:

```yaml
apiVersion: forjate.io/v0
kind: UseCase
metadata:
  name: db-migration-a-to-b        # must equal the directory name
spec:
  isolation: shared                # shared | dedicated
  ttl: 4h                          # how long before gc reclaims it
  components:                      # inventory, for humans and for review
    - apps/databases/postgres
    - apps/databases/mongodb
  jobs:
    seed:   { name: dbmig-seed,     timeout: 300 }
    run:    { name: dbmig-migrate,  timeout: 600 }   # optional
    verify: { name: dbmig-validate, timeout: 300 }
  outputs:
    endpoints:
      - { name: source, service: postgres, port: 5432,  protocol: postgresql }
      - { name: target, service: mongodb,  port: 27017, protocol: mongodb }
    secrets:
      - { name: source-credentials, secretRef: postgres-secret,
          keys: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD] }
      - { name: target-credentials, secretRef: mongodb-secret,
          keys: [MONGO_INITDB_ROOT_USERNAME, MONGO_INITDB_ROOT_PASSWORD] }
```

Field by field:

| Field | Why it exists |
|-------|---------------|
| `metadata.name` | Identity. Must match the directory name — CI asserts it, so the runner can go from a name on the command line to a path on disk without a lookup table. |
| `spec.isolation` | Selects the isolation strategy. See [Isolation](#isolation-shared-vs-dedicated). |
| `spec.ttl` | Consumed by `gc`. `<N>m`, `<N>h`, or `<N>d`. Ephemeral is a promise the tooling has to keep. |
| `spec.components` | Declarative inventory of which catalog components the use case pulls in. Not consumed by the runner — it's for reviewers and for the catalog. |
| `spec.jobs` | The lifecycle. `seed` and `verify` are mandatory; `run` is the optional middle step where the use case's actual work happens. Names must match Jobs in the built manifest (CI asserts this too). |
| `spec.outputs` | **The agent-facing part.** Endpoints and credential references, so nothing has to be discovered by trial and error. |

**Endpoint DNS is derivable, never guessed.** Given a use case named `<name>` and an endpoint with `service: <svc>` and `port: <port>`, the in-cluster address is always:

```
<svc>.uc-<name>.svc.cluster.local:<port>
```

The runner prints the resolved endpoints when `up` completes. An agent reads `spec.outputs`, applies the rule, and connects.

`usecase.yaml` is not referenced by any `kustomization.yaml`, so it is invisible to `kustomize build` and to `kubeconform`. It is validated separately against a JSON Schema (`scripts/ephemeral/usecase.schema.json`).

### Why `jobs.run` is deliberately vague

`run` is a slot, not a specification. The db-migration example could fill it with a Python ETL Job today and an Airbyte connector Job once that component lands in the catalog — the contract, the runner, the CI gate, and any agent consuming the environment stay untouched. **The architecture commits to the lifecycle, not to the mechanism.**

## Lifecycle

```
ephemeral.sh up <name>
  │
  ├─ preflight        deps (k3d, kubectl, kustomize, yq), contract schema, name == dir
  ├─ ensure cluster   shared: reuse forjate-uc-shared   dedicated: create forjate-uc-<name>
  ├─ seed secrets     cp secrets/*.env.example → *.env when missing (same as CI does)
  ├─ apply overlay    kustomize build | kubectl apply   (retry once after 3s — CRD establishment)
  ├─ stamp TTL        annotate ns forjate.io/expires-at=<now + spec.ttl>
  ├─ run seed  ──┐
  ├─ run run   ──┤    delete Job (immutable) → apply → wait Complete|Failed|Timeout → print logs
  ├─ run verify ─┘    BLOCKS until verify exits 0
  └─ print outputs    resolved endpoints + secret names from spec.outputs
```

The blocking verify is what makes this usable by an agent: `up` returning 0 *means* the environment works. There is no "wait a bit and hope" step.

Other subcommands:

| Command | What it does |
|---------|--------------|
| `up <name>` | The full flow above. Idempotent — re-running redeploys and re-runs all Jobs. |
| `seed <name>` / `validate <name>` | Re-run just that Job against a live environment. The tight inner loop while developing a use case. |
| `down <name>` | Delete the namespace (shared) or the whole cluster (dedicated). |
| `ls` | Everything currently alive, with time remaining. |
| `gc [--dry-run]` | Reclaim everything past its TTL. |

## Isolation: shared vs dedicated

Two strategies, declared per use case, same overlay either way.

| | `shared` | `dedicated` |
|---|---|---|
| **Cluster** | `forjate-uc-shared`, created on first use, reused | `forjate-uc-<name>`, one per use case |
| **Kubeconfig** | `~/.kube/forjate-uc-shared.yaml` | `~/.kube/forjate-uc-<name>.yaml` |
| **Namespace** | `uc-<name>` | `uc-<name>` |
| **TTL tracked by** | `forjate.io/expires-at` annotation on the namespace | cluster creation time vs. the contract's `spec.ttl` |
| **`down`** | delete the namespace | `k3d cluster delete` + remove kubeconfig |
| **Startup cost** | seconds after the first one | ~1–2 min per use case |
| **Teardown confidence** | good | total |

**The rule: if a use case installs CRDs, operators, or StorageClasses, it must declare `dedicated`.** Those are cluster-scoped and they outlive namespace deletion — a shared cluster accumulates them as residue and the next use case inherits a dirty environment. Everything else defaults to `shared`.

There is no state file. Namespace annotations and k3d cluster metadata are the single source of truth, which means `ls` and `gc` still work correctly after a machine restart, a `git checkout`, or a session that was killed halfway through.

The shared cluster is never garbage-collected — it is cheap to keep and expensive to recreate. Only namespaces inside it expire.

## What the tooling provides

```
scripts/ephemeral/
  ephemeral.sh          # up | seed | validate | down | ls | gc
  create-usecase.sh     # scaffolds a new use case from templates
  usecase.schema.json   # the contract, formalized
  lib/                  # log, deps, cluster, usecase, job — the repo's first shared shell lib
```

`create-usecase.sh --name my-case` produces a complete, runnable skeleton: contract, kustomizations, namespace, stub seed/run/verify Jobs, `.env.example` files, README, `.gitignore`. The intended workflow is scaffold → wire in components → fill the Jobs, never start from a blank directory.

The `lib/` split is also a cleanup. Logging helpers, dependency preflight, k3d bootstrap, and the delete-apply-wait-log Job cycle are currently copy-pasted across five overlay script sets. The runner consolidates them; migrating the existing overlays onto the same library is a follow-up.

## Validation

The pattern validates itself in CI (`.github/workflows/validate-usecases.yml`):

| Gate | What it proves |
|------|----------------|
| **Contract lint** | Every `usecase.yaml` matches the schema, `metadata.name` equals its directory, and every Job named in `spec.jobs` actually exists in the built manifest. Catches contract drift before it reaches a runner. |
| **Shellcheck** | The runner and scaffolder are statically sound. |
| **End-to-end smoke** | A real k3d cluster on the runner: `up` → `ls` → `down`, asserting the namespace is gone. The lifecycle is proven unattended, on every change. |

The existing `validate-kustomize.yml` gate covers the overlay manifests themselves — it discovers any directory with a `kustomization.yaml` under `k8s/overlays` recursively, so use cases are picked up with no workflow changes.

## Where this goes

The current scope is deliberately the skeleton: contract, runner, scaffolder, CI, and one example use case whose Jobs are stubs. What it proves is the lifecycle, not any particular workload.

Natural next steps, roughly in order:

- **Fill the example.** A real synthetic dataset in the seed Job and a real migration in the run Job, so `db-migration-a-to-b` becomes a working reference rather than a shape.
- **Airbyte as a component.** Already marked planned in the catalog. Once it exists, the migration use case swaps its `run` Job for a connector-driven one and the contract doesn't move.
- **More use cases.** Document ingestion into a vector store, event-driven pipelines through the existing CDC components, agent orchestration on Temporal — each one a directory, each one `up`-able in a command.
- **Consolidate the overlay scripts** onto `scripts/ephemeral/lib/`, retiring five copies of the same logging block.
- **Remote consumption.** Tenants outside this repo already pull `base` and `components` over SSH. Use cases could be consumed the same way, letting a separate agent-playlist repo spin up Forjate environments without vendoring them.

## Open questions

- **Base weight.** Use-case overlays include `../../../base` per the overlay convention, which brings Traefik, cert-manager, and the MinIO operator along. For a use case that only needs two databases this is dead weight on `up` latency. Making the base optional for use cases would help, at the cost of a second composition rule to explain.
- **Shared-cluster lifetime.** Never collecting `forjate-uc-shared` is the right default for a laptop. On a longer-lived machine it may want its own periodic reset.
- **Concurrency.** Nothing today prevents two `up` runs against the shared cluster at once. They target different namespaces so it should be safe, but it is untested.

# Overlay convention

What every overlay in `k8s/overlays/` is expected to ship, in three tiers. The tier is a **promise to the operator**, not a hierarchy of quality — a Lab tier overlay can be perfect for what it does, an Advanced tier overlay is just one you'd bet a paying customer on.

## Tiers at a glance

| Tier | Promise | Read | Run | Recover |
|------|---------|------|-----|---------|
| **Mínimo** | "Here's what it does and how it composes" | Doc + diagram + README + index entry | Manual `kubectl kustomize \| kubectl apply` | You handle it |
| **Recommended** | "Safe to deploy without surprises" | Mínimo + namespace contract + hardening notes | Reproducible local cluster (k3d/kind) | Documented rollback steps |
| **Advanced** | "Battle-tested operability" | Recommended + per-namespace structure + secrets contract | Bootstrap scripts (`01_init.sh`, `02_deploy.sh`, `destroy.sh`) | Validation job (`*-validate-job.yaml`) that proves the overlay actually works |

## Tier Mínimo — required for every overlay

If an overlay doesn't have all of this, it doesn't go in the catalog.

1. **`k8s/overlays/<name>/kustomization.yaml`** — builds cleanly with `kubectl kustomize` (CI gate).
2. **`k8s/overlays/<name>/README.md`** — one paragraph + a pointer to the design doc + the build/deploy command.
3. **`docs/overlays/<name>.md`** — design doc following the [overlay template](#overlay-design-doc-template) below.
4. **`docs/assets/architecture/overlay-<name>.png`** — diagram (cyberpunk-terminal style — see existing diagrams for the language).
5. **`docs/assets/architecture/overlay-<name>.prompt.md`** — versioned prompt that produced the diagram (so it's regenerable).
6. **Entry in `docs/overlays/README.md`** — the catalog index, with a clear tier label and a one-line "best for" description.

## Tier Recommended — adds production-shaped defaults

On top of Mínimo:

7. **`k8s/overlays/<name>/namespace.yaml`** — overlay declares its own namespace explicitly (no implicit `namespace:` global on the kustomization, which collides with base namespaces).
8. **Resource requests + limits** on every custom Deployment / StatefulSet shipped by the overlay (not upstream charts).
9. **Liveness + readiness probes** on every custom workload.
10. **`securityContext` compatible with Pod Security Admission `restricted`** on custom workloads:
    ```yaml
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities: { drop: [ALL] }
      runAsNonRoot: true
      runAsUser: 1000
      seccompProfile: { type: RuntimeDefault }
    ```
11. **`.gitignore`** in the overlay dir to keep real `.env` files out, allowing `*.env.example` through:
    ```
    secrets/*.env
    !secrets/*.env.example
    ```

## Tier Advanced — adds operability

On top of Recommended:

12. **Per-namespace structure**: when an overlay touches more than one namespace, each gets its own subdirectory under `namespaces/<ns>/` with its own `kustomization.yaml`, `secrets/`, `patches/`, `configs/`. The root `kustomization.yaml` composes them. This is the pattern already used by `ai-dev-stack`, `agentic-orchestration`, `cdc-event-sourcing`.
13. **`.env.example` files committed for every `.env` consumed by `secretGenerator`**, named in the same path. This is what lets CI seed placeholder secrets via `cp *.env.example *.env` and validate the build.
14. **Bootstrap scripts** in the overlay dir:
    - `01_init_cluster.sh` — opinionated cluster bootstrap (k3d, k3s, kind, etc.) for the target environment.
    - `02_deploy.sh` — apply the overlay (and any Helm charts the overlay depends on outside Kustomize).
    - `destroy.sh` (or equivalent) — tear it all down cleanly.
15. **Validation job** — a Kubernetes `Job` resource named `<purpose>-validate` (e.g. `cdc-validate-job.yaml`) that:
    - Runs after deploy.
    - Exercises the overlay's defining capability end-to-end (e.g. CDC overlay → write to source DB → assert message lands in broker).
    - Exits 0 on success, non-zero on failure.
    - Has `ttlSecondsAfterFinished` so it cleans up automatically.
    The doc must include the **runbook** for reading its output.

## Overlay design doc template

Every `docs/overlays/<name>.md` follows this shape:

```markdown
# Overlay: `<name>`

> One-sentence pitch. The kind of one-liner you'd put on a slide.

## The situation

Two or three paragraphs. What problem does this overlay solve? Who would use it?
What's the trigger to reach for THIS overlay vs another?

## Architecture

![<Name>](../assets/architecture/overlay-<name>.png)

## Components used

| Component | Why |
|-----------|-----|
| `apps/...` | What role it plays in this overlay |
| ...        | ... |

## `kustomization.yaml`

(snippet of the actual file or its essential structure)

## Notes

Operational gotchas, scaling notes, migration paths, when NOT to use this overlay.
```

Two screens max. If a doc grows past that, it should be split into a follow-up doc that the overlay doc links to.

## Use-case overlays (ephemeral)

A **use case** is an overlay with a shorter life expectancy: it exists to give an agent or a demo a real environment to work against, and it is expected to be destroyed. Use cases live under `k8s/overlays/usecases/<name>/` and follow the tiers above with four changes.

Full design: [`docs/ephemeral-use-cases.md`](../ephemeral-use-cases.md). Operator reference: [`scripts/ephemeral/README.md`](../../scripts/ephemeral/README.md).

**1. A contract is mandatory.** Every use case ships a `usecase.yaml` at its root, validated in CI against [`scripts/ephemeral/usecase.schema.json`](../../scripts/ephemeral/usecase.schema.json). It declares isolation, TTL, the three lifecycle Jobs, and — the part that matters for agents — the endpoints and credential Secrets the environment exposes. `metadata.name` must equal the directory name.

**2. Namespace naming is fixed.** A use case owns exactly one namespace, `uc-<name>`, declared in `namespaces/uc-<name>/namespace.yaml`. The runner stamps ownership labels and a `forjate.io/expires-at` annotation on it at deploy time; nothing else may.

**3. Seed and verify Jobs are mandatory; `run` is optional.** All three ship `spec.suspend: true` so that applying the overlay creates them without starting them — the runner imposes the order. The verify Job is the tier-Advanced validation Job under a different name and follows the same convention (`<purpose>-validate`, `backoffLimit: 0`, `ttlSecondsAfterFinished`, a `check` helper with PASS/FAIL counters and a trailing test as the exit status).

**4. No bootstrap scripts.** Advanced tier item #14 does not apply: use cases must **not** ship `01_init_cluster.sh`, `02_deploy.sh` or `destroy.sh`. The shared runner replaces them.

```bash
./scripts/ephemeral/create-usecase.sh --name my-use-case --ttl 2h
./scripts/ephemeral/ephemeral.sh up my-use-case
```

### Choosing isolation

`spec.isolation: shared` puts the use case in a namespace on a single reusable cluster. `spec.isolation: dedicated` gives it a cluster of its own.

**Declare `dedicated` when the use case installs CRDs, operators or StorageClasses.** Those are cluster-scoped and survive namespace deletion, so on a shared cluster they accumulate as residue that the next use case inherits. Everything else stays `shared`.

## Tier matrix per overlay (current state)

See [`docs/overlays/README.md`](./README.md) for the live table. As of this convention's introduction:

| Overlay | Current tier | Target tier | Gap |
|---------|--------------|-------------|-----|
| `agentic-simple-workflow` | Recommended | Recommended | — |
| `bare-metal-starter` | Advanced | Advanced | — (promoted with bootstrap scripts + validation Job) |
| `home-edge-lab` | Advanced | Advanced | — (promoted with bootstrap scripts + Mosquitto/HA/MinIO smoke validation Job) |
| `multi-cloud-portable` | Recommended | Recommended | — |
| `multi-tenant-pattern` | Recommended | Recommended | — |
| `ai-dev-stack` | Advanced (legacy) | Advanced | doc + diagram (this PR) |
| `agentic-orchestration` | Advanced (legacy) | Advanced | doc + diagram (this PR) |
| `cdc-event-sourcing` | Advanced (legacy) | Advanced | doc + diagram (this PR) |

"Legacy" here just means "predates the convention" — the patterns these three established (per-namespace structure, validation jobs, bootstrap scripts) are exactly what got promoted to define the Advanced tier.

## CI enforcement

The `validate-kustomize` workflow already enforces tier Mínimo (#1). Future passes will check:

- Mínimo #2-6 (presence of README, design doc, diagram, prompt, index entry) — `lint-overlay-catalog.sh`.
- Recommended #7-11 (kustomize build output contains a Namespace resource per overlay, all custom Deployments have probes + resources + restricted securityContext).
- Advanced #14-15 (presence of `01_init_cluster.sh`, `02_deploy.sh`, validation job — for overlays declared as Advanced in the index).

Until those checks exist, the convention is enforced by review.

Use-case overlays are the exception: the `validate-usecases` workflow already enforces their extra rules (contract schema, identity matching the directory, declared Jobs existing and shipping suspended), and proves the lifecycle end-to-end on a real k3d cluster.

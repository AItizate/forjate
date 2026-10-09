# Overlay checklist (condensed from docs/overlays/CONVENTION.md)

Tick every line of the tier the stage planner assigned. Crawl use cases ship at **Mínimo + the use-case contract**; Walk at **Recommended**; Run at **Advanced**.

## Mínimo (every overlay)

- [ ] `kustomization.yaml` builds with `kustomize build --enable-helm`
- [ ] `README.md`: one paragraph, link to the design doc, build/deploy command
- [ ] `docs/overlays/<name>.md` design doc (for use cases: the `.builder/` report stands in until the use case graduates to a catalog overlay)
- [ ] entry in `docs/overlays/README.md` when it is a catalog overlay

## Use-case contract (Crawl)

- [ ] `usecase.yaml` validates against `scripts/ephemeral/usecase.schema.json`
- [ ] `metadata.name` == directory name
- [ ] `spec.jobs.seed` and `spec.jobs.verify` exist as Jobs in the built manifest, `spec.suspend: true`
- [ ] `spec.outputs.endpoints` list every service an agent will connect to
- [ ] `spec.outputs.secrets` list every Secret and its keys
- [ ] `spec.isolation: dedicated` if the overlay installs CRDs, operators or StorageClasses
- [ ] `ttl` set

## Recommended (Walk)

- [ ] `namespace.yaml` explicit, no global `namespace:` on the root
- [ ] requests + limits on every custom Deployment/StatefulSet/Job
- [ ] liveness + readiness probes on custom workloads
- [ ] `securityContext` compatible with PSA `restricted` on custom workloads (`allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`, `runAsNonRoot: true`, `seccompProfile.type: RuntimeDefault`)
- [ ] `.gitignore` keeps real `.env` out, lets `*.env.example` in

## Advanced (Run)

- [ ] per-namespace structure under `namespaces/<ns>/` with own `secrets/`, `patches/`, `configs/`
- [ ] `.env.example` for every `.env` consumed by a `secretGenerator`
- [ ] bootstrap scripts: `01_init_cluster.sh`, `02_deploy.sh`, `destroy.sh`
- [ ] validation Job `<purpose>-validate` with `ttlSecondsAfterFinished`, runbook in the doc

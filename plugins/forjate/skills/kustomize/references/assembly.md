# Assembling a use case from its records

`scripts/assemble.py` is the deterministic half of the assembly: it reads `.builder/` (brief, stage plan, every decision record, `gates.yaml`, `scaffold.yaml`) and writes what the records state. You are the other half: you read what it wrote, fill what a record left open, run the builds and the gates, and report verbatim.

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/skills/kustomize/scripts/assemble.py <usecase-dir> [--force]
```

Existing files are kept (a Job someone edited survives a re-run); `--force` overwrites.

## What it writes, from which record

| Output | Source |
|--------|--------|
| `kustomization.yaml` (Crawl root: base, the Crawl infra components, `./namespaces/uc-<name>`, the overlay label) | every record's Crawl `choice` |
| `namespaces/uc-<name>/namespace.yaml` with PSA labels (warn and audit at `restricted`; `enforce` when the security record's Crawl `psa_level` is not `privileged`) | security |
| `namespaces/uc-<name>/kustomization.yaml`: the use-case-scoped components, the scaffold's Jobs and Deployments, `secretGenerator` per component Secret and per scaffold secret, laptop sizing patches, the glue a laptop needs (a Service for a component that ships a bare workload, an `envFrom` patch for a Secret its manifests never reference, an emptyDir in place of a hostPath, a GPU limit dropped when the catalog says the GPU is optional), `images: [{name, newTag: dev}]` | choices, `scaffold.yaml`, the catalog's `wiring` facts (contracts.md, "Component properties") |
| `namespaces/uc-<name>/<workload>.yaml`: Jobs (suspended, backoffLimit per phase, ttl, restricted-compatible contexts, emptyDir per `writable_paths`, `envFrom` the Secrets) and Deployments with their Service and probes | `scaffold.yaml` workloads |
| `secrets/<name>.env.example` with the `# To generate:` / `# To seal:` header | component Secrets, scaffold secrets, the integrations of later stages |
| `usecase.yaml`: contract (jobs from the scaffold's phases, endpoints and secrets of the components and the Deployments, `spec.build` for the image) | scaffold, choices, brief |
| `stages/walk/`: recomposes the Crawl root (base + Crawl infra + `../../namespaces/uc-<name>`), deletes through `relocated/` every Crawl component no Walk record repeats (superseded by one of the same capability, or dropped; its Secret leaves with it), adds the Walk infra at its root and the Walk-scoped components under `namespaces/uc-<name>/`, the PSA patch, `MODEL_MODE=live` and the real system URLs on the workloads, `$patch: delete` for every generated Secret and the component placeholders, one `sealed-<name>.yaml` placeholder + `.env.example` per secret, `netpols.yaml`, the surface Ingress behind the auth middleware and the component Ingresses patched with it, `argocd/application.yaml` with the repo-server SSH wiring, `images:` with the registry path and a SHA placeholder | security (`psa_level`, `secrets_mechanism`, `network_policy`, `egress_allowlist`, `auth_in_front`, `image_policy`), devops (`gitops`, `argocd_sync`, `argocd_private_refs`, `image_registry`), ux (`surface_workload`), architecture (`integrations`) |
| From Walk, every namespace at its own level: the shared namespaces (label patch, or a Namespace the assembly declares, or a namespace sub-overlay that places a component whose manifests set none), the PSA exception namespaces with the components they receive, their Secrets and default-deny policies, `relocated/` when a component already in the build moves, and `namespaces/uc-<name>/aliases.yaml` | security (`psa_level`, `psa_exceptions`), the catalog (`namespace`, `namespace_how`, `psa_level`) |
| `stages/run/`: extends `../walk`, adds the Run infra and scoped components, PSA, `ExternalSecret` per secret (deleting the SealedSecrets) when the mechanism moves to `external-secrets`, the Run Application, `images:` with a digest placeholder | same records at Run |
| `README.md`: the decision table (per area and stage), open questions, the gates table with counts, the checklist, the assembly notes | everything |

Why a stage overlay recomposes the root instead of referencing `../..`: kustomize refuses a resource that is an ancestor of the current directory ("cycle detected"), so `stages/walk` lists `../../../../../base`, the Crawl infra components and `../../namespaces/uc-<name>`; `stages/run` lists `../walk`, a sibling. The result is the same manifest plus the stage's additions, and both build on their own.

## Namespaces and PSA exceptions

The use case's namespace enforces the security record's `psa_level` and nothing else changes it. Every other namespace is labelled at its own level, from facts the catalog derives from `k8s/**` (`wiki/catalog.json`: `namespace`, `namespace_how`, `psa_level`), so a component that changes its namespace or its pods changes the assembly with no edit here:

- **Shared infrastructure** is a component whose catalog `namespace` is set. Its namespace gets `enforce` at the least strict `psa_level` of the components the stage runs there (warn and audit at `restricted`). `namespace_how` says how: `declares` or `remote`, a label patch (a patch that matches nothing is a no-op); `sets`, the assembly declares the Namespace; `none`, the assembly places the component with a namespace sub-overlay and declares it. A component that ships a Namespace the build already has is wrapped so the duplicate is dropped. Kubernetes' own namespaces (`kube-system`, `default`, ...) are never labelled, and a namespace whose level the catalog does not know is left to its owner with a note.
- **A PSA exception** is an entry of the security record's `psa_exceptions`. A use-case-scoped component it lists leaves `uc-<name>` for the entry's namespace: composed straight there when the stage adds it, moved by `stages/<stage>/relocated/` (a JSON patch per object on `metadata.namespace`) when it is already in the build, because the aliases left behind would collide with the originals in one kustomization. The exception namespace is declared at the entry's level with the owner and the reason as annotations, gets the component's Secret (sealed per namespace, or an ExternalSecret at Run), default-deny with DNS, traffic inside it, `uc-<name>` to the components' ports and the ingress controller to what it serves, and `uc-<name>` gets an ExternalName alias per moved Service. The auth middleware reference follows the identity provider to its namespace.

What the assembly reports instead of deciding: a shared namespace below the use case's level with no entry, an entry whose level disagrees with the catalog (the label follows the catalog), a component whose shipped pods meet less than its exception namespace enforces (confirm the overlay's patches), a component moved at Walk that the Run record places elsewhere (stage overlays never move a component back).

## What you check after it ran

1. `kustomize build --enable-helm` and `kubeconform` on the root and on every `stages/*`; a build that passes with a warning is reported as such.
2. `validate.py` on the use case, `scaffold-check.py` when `app/` exists, `secret-scan.py` over the use case directory.
3. `scripts/gates/gates.py run <name> --transition 'crawl->walk' --only ci` (`psa-check` reads the use case's level and every labelled exception namespace against the record): every `ci` gate the records emitted has a check script and passes on what you wrote; a `skipped` needs the live environment or names something the overlay has no instance of (a LiteLLM config when no gateway is chosen), which you report, not hide.
4. The assembly notes (`note:` lines, also in the README): a surface workload the scaffold does not ship yet, a secret whose keys were guessed from an integration line, a matrix the security record requires at Run. Each becomes a line in your reply; none is silently dropped.
5. `./scripts/ephemeral/ephemeral.sh up <name>` when a cluster is acceptable: the verify Job's exit code is the Crawl gate.

## What the generator does not decide

The seed and verify logic (the scaffold's); the secrets' real values (the `.env.example` recipe); the hostnames (`*.example.com` placeholders to patch); the `targetRevision` of the Applications (the tag that will carry the overlay, `--factory-ref`); the per-workload egress matrix at Run (written by hand when the security record says `required`); a component whose catalog `wiring` has no `service` or whose Secret documents no keys (it is included as a resource with no endpoint or no `.env.example`, and the note says so: curate `wiring` in `wiki/catalog-overrides.yaml`, never in the script). Nothing in the generator names a component: a new catalog component with manifests the compiler can read is wired with no edit here.

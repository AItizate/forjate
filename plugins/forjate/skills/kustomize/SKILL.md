---
name: kustomize
description: How to write, extend, assemble and validate a Forjate overlay for a use case — component lookup in the catalog, the overlay convention tiers, namespace sub-overlays, patches, secrets via .env.example, the usecase.yaml contract for the ephemeral runner, Crawl/Walk/Run stage overlays, the assembly of a complete overlay from a use case's decision records (NetworkPolicies, PSA labels, sealed secrets, the ArgoCD Application, images as the write-back surface) and the tenant-root target that im-u and globant consume. Use this whenever any forjate skill has to emit or modify kustomization.yaml, a patch, a Secret or ConfigMap generator, a Job for seed/run/verify, or a usecase.yaml, whenever a use case's records and gates are ready and the overlay has to be assembled, whenever a use case has to land in a tenant repo, and whenever someone asks to add a component to an overlay, turn a component list into an overlay, or make an overlay build and pass CI.
user-invocable: true
argument-hint: "[new <usecase> | add <component> to <overlay> | check <overlay>]"
allowed-tools: Read Grep Glob Write Edit Bash(kustomize *) Bash(kubectl kustomize *) Bash(kubeconform *) Bash(poetry run python *) Bash(python3 *) Bash(./scripts/ephemeral/*) Bash(yq *) Bash(cp *) Bash(ls *) Bash(cat *) Bash(find *)
---

# Writing Forjate overlays

You are the only skill in the forjate plugin that writes Kubernetes YAML. Experts decide; you make the decision buildable. Everything you emit must satisfy `docs/overlays/CONVENTION.md` and, for use cases, `docs/ephemeral-use-cases.md`. Read `references/checklist.md` before the first file and again before you declare the overlay done.

## Find components in the catalog, never by guessing paths

`wiki/catalog.json` is the machine-readable catalog: one record per component with `path` (relative to `k8s/components/`), images, kinds, what it composes, who consumes it, and curated facts (`stages`, `capabilities`, `gpu_required`, `ha`, `psa_restricted`, `secrets`, `data_classes`, `licence`, `maturity`, `notes`; the vocabulary is `wiki/catalog-capabilities.yaml` and `references/catalog-snapshot.md` is what it resolves today). Query it instead of walking the tree:

```bash
python3 -c "import json;[print(c['path'],c['stages'],c['capabilities']) for c in json.load(open('wiki/catalog.json'))['components'] if 'semantic-memory' in c['capabilities']]"
```

Then open `wiki/components/<name>.md` for the declared resources and `docs/apps/<name>.md` for how to configure it. A component that is not in the catalog does not exist for you; if an expert asked for one, hand back an open question instead of inventing a directory.

## Shape of a use-case overlay

```
k8s/overlays/usecases/<name>/
├── usecase.yaml                      # contract for scripts/ephemeral/ephemeral.sh
├── kustomization.yaml                # base + ./namespaces/uc-<name>   (Crawl)
├── namespaces/uc-<name>/
│   ├── kustomization.yaml            # namespace: uc-<name>; components; Jobs; generators; patches
│   ├── namespace.yaml
│   ├── <prefix>-seed-job.yaml        # suspended Jobs, see below
│   ├── <prefix>-run-job.yaml         # optional
│   ├── <prefix>-validate-job.yaml
│   ├── patches/*.yaml                # resource sizing for a laptop, image tags, hostnames
│   ├── configs/*                     # files for configMapGenerator
│   └── secrets/*.env.example         # committed; the real .env is gitignored and seeded by the runner
├── stages/walk/kustomization.yaml    # added when Walk is unlocked; extends ../.. with Walk-tier components
├── stages/run/kustomization.yaml
├── .gitignore                        # secrets/*.env, !secrets/*.env.example
├── .builder/                         # the builder's artifacts (brief, plan, decisions, gates)
└── README.md
```

Start from the scaffolder rather than from a blank file; it produces a buildable skeleton with the right names and suspended Jobs:

```bash
./scripts/ephemeral/create-usecase.sh --name <name> --ttl 4h --prefix <short>
```

Then wire in components, fill the Jobs, and add generators and patches. `k8s/overlays/usecases/db-migration-a-to-b/` is the reference implementation; mirror its layout.

## Rules that CI enforces

- **Builds clean**: `kustomize build --enable-helm k8s/overlays/usecases/<name>` and `kubeconform` on the output. Run both before you say done.
- **Contract matches the overlay**: `metadata.name` equals the directory; every Job in `spec.jobs` exists in the built manifest and ships `spec.suspend: true` (the runner un-suspends them in order).
- **Secrets**: every `.env` a `secretGenerator` reads, and every `sealed-*.yaml` from Walk, has a committed `.env.example` with placeholder values at the same path and a header carrying the `# To generate:` and `# To seal:` commands (the security skill's rule; the recipe travels with the secret). CI and the runner `cp` examples to real files. From Walk a factory placeholder Secret is removed with `$patch: delete` and replaced by a SealedSecret of the same name (`references/patterns.md`). No plaintext credential anywhere else: `plugins/forjate/scripts/builder/secret-scan.py <usecase-dir>` runs in CI (`validate-kustomize`) and as the `secret-scan` gate over `configMapGenerator` literals, `configs/`, patches, env values and tracked `.env` files.
- **Namespace**: declared explicitly in `namespace.yaml`; the sub-overlay sets `namespace: uc-<name>`. Never put a global `namespace:` on the root kustomization, it collides with base namespaces.
- **Component secrets**: catalog databases leave their Secret out and expect the overlay to supply one with the exact name they mount (`postgres-secret`, `mongodb-secret`). Check the component's wiki page for the name and keys.
- **Sizing**: catalog defaults are sized for tenants. Add `patches/<component>-resources.yaml` for Crawl so it fits k3d on a laptop.

## Assembling from the records

When the use case has its `.builder/` (records, `gates.yaml`, `scaffold.yaml`), do not write the overlay by hand: run the generator, then review, fill and verify what it wrote (`references/assembly.md`):

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/skills/kustomize/scripts/assemble.py <usecase-dir>                      # the overlay target
poetry run python ${CLAUDE_PLUGIN_ROOT}/skills/kustomize/scripts/assemble.py <usecase-dir> --target tenant \
    --tenant-repo <iac-repo> --tenant <name> --factory-ref <tag>                                                # the tenant-root shape
```

It writes the Crawl root, the namespace child with the components, the scaffold's Jobs and Deployments, the `.env.example` recipes, `usecase.yaml` with `spec.build`, `stages/walk` and `stages/run` with the PSA labels (the use case's namespace at the stage's level, every shared namespace at its own, the security record's PSA exceptions moved to theirs), the NetworkPolicies and the egress allow-list the security record demands, the sealed-secret placeholders replacing every generated Secret, the ArgoCD Application with the repo-server wiring, `images:` as the write-back surface, and the README with the decision summary. Then you run the builds, `validate.py`, `scaffold-check.py`, `secret-scan.py` and `gates.py run <name> --transition 'crawl->walk' --only ci`, and every `note:` it printed is a line in your reply. The tenant target (`references/tenant-target.md`) emits the shape a real tenant consumes: SSH refs pinned to one tag, `./namespaces/uc-<name>`, `$patch: delete` for every placeholder Secret, the Application and the SSH wiring at Walk.

## Stage overlays

Crawl is the root overlay. Walk and Run are overlays on the overlay, so the Crawl manifest stays the thing that was proven on the ephemeral cluster. kustomize refuses a resource that is an ancestor of the current directory (`../..` from `stages/walk` is a "cycle"), so a stage overlay recomposes the root from its parts:

```yaml
# stages/walk/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../../../base                       # what the root lists, minus the root itself
  - ../../namespaces/uc-<name>                # the Crawl namespace child
  - ../../../../../components/apps/sealed-secrets
  - ../../../../../components/apps/continuous-delivery/argocd
  - ./namespaces/uc-<name>                    # what Walk adds inside the namespace: policies, sealed secrets, components
patches:
  - path: patches/namespace-psa-patch.yaml
    target: { kind: Namespace, name: uc-<name> }
labels:
  - pairs: { app.kubernetes.io/managed-by: kustomize, app.kubernetes.io/overlay: <name> }
```

`stages/run/kustomization.yaml` lists `../walk` (a sibling) and adds only what changes at Run.

Each stage overlay adds what the decision records require for that stage (`forjate:devops`, `forjate:security`) and nothing the stage planner put out of scope. From Walk the security record's `network_policy: default-deny`, `egress_allowlist`, `psa_level` and `security_context` are written as manifests and labels unprompted (`references/patterns.md`); they are decisions, not options. A stage overlay must build on its own and differ from the root: `kustomize build k8s/overlays/usecases/<name>/stages/walk`. Remote refs in a stage overlay carry `?ref=<tag>`, never a branch.

## Validate everything

```bash
kustomize build --enable-helm k8s/overlays/usecases/<name> | kubeconform -strict -ignore-missing-schemas -
poetry run python plugins/forjate/scripts/builder/validate.py k8s/overlays/usecases/<name>
./scripts/ephemeral/ephemeral.sh up <name>      # when a cluster is acceptable; blocks until verify exits 0
```

Report results verbatim. A build that passes with a warning is a build that passes with a warning, not a clean build.

## Context packs

Before reasoning about the use case, resolve the packs that apply to you:

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/packs.py resolve --for kustomize --usecase-dir <usecase-dir>
```

Treat `must` entries as hard constraints: never decide against one, and if the use case cannot be served within it, raise an `open_questions` entry with `caused_by_rule` instead of bending the rule. Treat `should` entries as the default, deviating only with an explicit reason in `rationale`. Mention `may` entries when relevant. Cite every ref that shaped a stage decision in that stage's `constrained_by`. Open a guideline file only when its summary matters to the decision at hand. If the resolver reports an override of a `must`, say so in your record so it lands in `gates.yaml`. With no packs active, the factory defaults apply and your rationale says so.

Full rules: `forjate:context-pack`. For you the packs that matter most are naming patterns (`naming_pattern` on `namespace`) and required or denied components.

## See also

- `references/assembly.md`: what `scripts/assemble.py` writes from which record, what you check afterwards, what it does not decide.
- `references/tenant-target.md`: the tenant-root shape for `--target tenant`, and how to check it against the factory at the pinned tag.
- `references/checklist.md`: the tier checklist, condensed from `docs/overlays/CONVENTION.md`.
- `references/patterns.md`: patch and generator snippets that recur across overlays, plus what a real tenant does (tenant root shape, both SSH URL forms, placeholder-Secret replacement, patch naming, index-based env patches, default-deny NetworkPolicy).
- `docs/ephemeral-use-cases.md`, `scripts/ephemeral/README.md`: the runner and the contract, in full.

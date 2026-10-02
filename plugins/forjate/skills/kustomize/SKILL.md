---
name: kustomize
description: How to write, extend and validate a Forjate overlay for a use case — component lookup in the catalog, the overlay convention tiers, namespace sub-overlays, patches, secrets via .env.example, the usecase.yaml contract for the ephemeral runner, and Crawl/Walk/Run stage overlays. Use this whenever any forjate skill has to emit or modify kustomization.yaml, a patch, a Secret or ConfigMap generator, a Job for seed/run/verify, or a usecase.yaml, and whenever someone asks to add a component to an overlay, turn a component list into an overlay, or make an overlay build and pass CI.
user-invocable: true
argument-hint: "[new <usecase> | add <component> to <overlay> | check <overlay>]"
allowed-tools: Read Grep Glob Write Edit Bash(kustomize *) Bash(kubectl kustomize *) Bash(kubeconform *) Bash(poetry run python *) Bash(./scripts/ephemeral/*) Bash(yq *)
---

# Writing Forjate overlays

You are the only skill in the forjate plugin that writes Kubernetes YAML. Experts decide; you make the decision buildable. Everything you emit must satisfy `docs/overlays/CONVENTION.md` and, for use cases, `docs/ephemeral-use-cases.md`. Read `references/checklist.md` before the first file and again before you declare the overlay done.

## Find components in the catalog, never by guessing paths

`wiki/catalog.json` is the machine-readable catalog: one record per component with `path` (relative to `k8s/components/`), images, kinds, what it composes, who consumes it, and curated facts (`stages`, `roles`, `licence`, `maturity`, `notes`). Query it instead of walking the tree:

```bash
python3 -c "import json;[print(c['path'],c['stages'],c['roles']) for c in json.load(open('wiki/catalog.json'))['components'] if 'vector' in c['roles']]"
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
- **Secrets**: every `.env` a `secretGenerator` reads has a committed `.env.example` with placeholder values at the same path. CI and the runner `cp` examples to real files.
- **Namespace**: declared explicitly in `namespace.yaml`; the sub-overlay sets `namespace: uc-<name>`. Never put a global `namespace:` on the root kustomization, it collides with base namespaces.
- **Component secrets**: catalog databases leave their Secret out and expect the overlay to supply one with the exact name they mount (`postgres-secret`, `mongodb-secret`). Check the component's wiki page for the name and keys.
- **Sizing**: catalog defaults are sized for tenants. Add `patches/<component>-resources.yaml` for Crawl so it fits k3d on a laptop.

## Stage overlays

Crawl is the root overlay. Walk and Run are overlays on the overlay, so the Crawl manifest stays the thing that was proven on the ephemeral cluster:

```yaml
# stages/walk/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../..
  - ../../../../../components/apps/sealed-secrets
  - ../../../../../components/apps/continuous-delivery/argocd
patches:
  - path: patches/psa-restricted.yaml
    target: { kind: Namespace, name: uc-<name> }
```

Each stage overlay adds what the decision records require for that stage (`forjate:devops`, `forjate:security`) and nothing the stage planner put out of scope. A stage overlay must build on its own: `kustomize build k8s/overlays/usecases/<name>/stages/walk`.

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

- `references/checklist.md`: the tier checklist, condensed from `docs/overlays/CONVENTION.md`.
- `references/patterns.md`: patch and generator snippets that recur across overlays.
- `docs/ephemeral-use-cases.md`, `scripts/ephemeral/README.md`: the runner and the contract, in full.

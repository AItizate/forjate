# Use-case builder: overview

One session, one business problem, one deployable use case. The builder is a Claude Code plugin (`plugins/forjate/`) made of a coordinator, a stage planner, ten expert skills and two builders, all talking through schema-validated files under `k8s/overlays/usecases/<name>/`. This page is the map; `plan.md` is the history and the roadmap, `contracts.md` the artifacts, `experts.md` the experts one by one, `evals.md` how the skills are tested.

## The flow

```
/usecase "we want to automate X"
   │
   ▼  intake (≤ 6 questions: language, packs, success metric, data, actors, constraints)
.builder/brief.yaml + packs.yaml
   │
   ▼  forjate:stage-planner
.builder/stage-plan.yaml            Crawl / Walk / Run in scope, exit criteria, which experts run
   │
   ▼  forjate:business (alone), then nine experts in parallel
.builder/decisions/*.yaml           business, architecture, ai-engineering, data-store, data-pipeline,
   │                                security, compliance, quality, devops, ux
   ▼  validate.py: cross-record consistency (conflicts become open questions, never silent)
   │
   ▼  forjate:quality consolidate
.builder/gates.yaml                 every gate_to_next verbatim, a check per gate (verify-job | ci | metric | manual)
   │
   ▼  forjate:app-scaffold                 forjate:kustomize (assemble)
app/ + .builder/scaffold.yaml       kustomization.yaml, namespaces/, usecase.yaml, stages/walk, stages/run, README
   │
   ▼  ephemeral.sh up <name>        builds app/ into <name>:dev, seed -> run -> verify on k3d
   ▼  gates.py run <name> --transition 'crawl->walk'
report
```

Every arrow is a file in git, so a person can stop, read and change course at any step; `/usecase resume <name>` picks up from the last valid artifact.

## The pieces

| Piece | Kind | Does |
|-------|------|------|
| `forjate:coordinator` | user-invocable skill, `/usecase` | intake, orchestration, the report; `review` prints the report (and, inside a tenant repo, the drift between its `CLAUDE.md` and its tree first); `assemble` runs only the builders |
| `forjate:stage-planner` | skill + agent | the stage plan with observable exit criteria and the expert selection |
| ten experts | skill + agent each | a Decision record per area, per stage, with alternatives, risks, gates and the pack rules that shaped it |
| `forjate:app-scaffold` | builder skill + agent | the workload: entrypoints per architecture workload, typed tools per AI-engineering line, a model double for CI, seed and verify scripts, tests, Dockerfile, workflows that call the shared CI templates `@v1`; writes `scaffold.yaml` |
| `forjate:kustomize` | shared skill + agent | the overlay from the records (`scripts/assemble.py`), or the tenant-root shape (`--target tenant`); builds, validates, runs the ci gates |
| `forjate:context-pack` | shared skill | the one interface through which corporate rules reach every skill |
| `scripts/builder/validate.py` | CI | schemas, catalog, packs, cross-record consistency, gates consolidation, ci refs |
| `scripts/builder/secret-scan.py` | CI gate | plaintext credentials in generator literals, configs, patches, env values, tracked `.env` |
| `scripts/builder/scaffold-check.py` | CI gate | tool signatures match the record, templates pinned `@v1`, no hand-rolled build |
| `scripts/gates/gates.py` | runner | executes `gates.yaml` for a transition: `ci` checks from `scripts/gates/checks/`, the verify Job, metrics, manual gates listed |
| `.github/workflows/gates.yml` | reusable workflow | tenants run the gates by tag |

## Stages

| | Crawl | Walk | Run |
|---|---|---|---|
| proves | the automation on seeded data, one user, on k3d via `ephemeral.sh` | real users rely on it on one cluster under GitOps | SLAs, audits, multi-tenancy |
| secrets | `secretGenerator` from `.env.example` | the first ranked `secrets-mechanism` (Sealed Secrets today), every generated Secret deleted and replaced | the top-ranked mechanism (External Secrets today) pulling from a `secrets-store` (OpenBao) when a pack asks |
| hardening | restricted-compatible workloads, PSA warn/audit | PSA enforced, default-deny NetworkPolicies, egress allow-list, auth in front of every human surface | plus the per-workload matrix when required, pinned digests |
| delivery | the working tree, the TTL is the rollback | ArgoCD Application on a tag with selfHeal, image write-back into `images:` | prune after a dry run, signed images |
| model | the deterministic double in CI (`MODEL_MODE=replay` or `rules`), the local model for the demo | the live model | same |

## Two outputs

**Overlay** (`k8s/overlays/usecases/<name>/`): the Crawl root plus `stages/walk` and `stages/run` as overlays on the overlay, so the Crawl manifest proven on the ephemeral cluster never changes. Golden examples: `invoice-intake` (batch over PDFs, financial data, regulated pack) and `support-copilot` (chat agent on Telegram, pii, no packs).

**Tenant root** (`--target tenant <repo>`): the shape a real tenant consumes (`tenant-patterns.md`): a root pulling the factory by SSH ref pinned to one tag, `./namespaces/uc-<name>`, `$patch: delete` for every placeholder Secret replaced by a SealedSecret, the Application and the repo-server wiring, `images:` as the write-back surface.

## Context packs

A pack is a versioned bundle of rules (`deny_components`, `min_psa_level`, `data_egress`, …) and guidelines (tool development, a security baseline). Every skill resolves its packs before deciding, cites the rule that shaped a choice in `constrained_by`, and raises an open question with `caused_by_rule` when a rule cannot be satisfied. `validate.py` proves mechanically that no `must` was violated. Examples: `context-packs/examples/regulated-corp`, `solo-dev`.

## Where to start

- A user: `claude --plugin-dir ./plugins/forjate`, then `/usecase <problem>`; read `k8s/overlays/usecases/invoice-intake/README.md` to see what comes out.
- A reviewer: `.builder/decisions/<area>.yaml` and `.builder/gates.yaml`; `gates.py list <name>`.
- A contributor adding an expert: `how-to-add-an-expert.md`.
- The learning path: `docs/learning-path.md`, step 7.

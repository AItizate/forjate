# forjate plugin

The use-case builder team for Claude Code. Design and roadmap: [`docs/use-case-builder/plan.md`](../../docs/use-case-builder/plan.md).

```
plugins/forjate/
├── .claude-plugin/plugin.json   # manifest
├── skills/<role>/SKILL.md       # one skill per role, invoked as /forjate:<role>
├── agents/<role>.md             # subagent per expert; loads its skill, returns a Decision record
├── evals/<role>/evals.json      # L1 skill evals; fixtures/ holds golden briefs, plans, records, gates, scaffolds, packs
└── scripts/builder/             # packs.py, validate.py, secret-scan.py, scaffold-check.py, tenant-drift.py, schemas/, tests/

Roles today: coordinator, stage-planner, kustomize, context-pack (shared), the core experts business, architecture, ai-engineering, data-store, data-pipeline, the governance experts security, compliance, quality (also consolidates gates.yaml), devops, the ux expert, and the app-scaffold builder (`docs/use-case-builder/experts.md`, `overview.md`).
```

## Install

From this repo (local development):

```bash
claude plugin validate ./plugins/forjate
claude --plugin-dir ./plugins/forjate            # one session
```

From a tenant repo:

```bash
claude plugin marketplace add AItizate/forjate
claude plugin install forjate@forjate
```

## Tooling

```bash
poetry run python plugins/forjate/scripts/builder/packs.py lint context-packs/examples/*
poetry run python plugins/forjate/scripts/builder/packs.py resolve --for security --usecase-dir k8s/overlays/usecases/<name>
poetry run python plugins/forjate/scripts/builder/validate.py k8s/overlays/usecases/<name>
poetry run python plugins/forjate/scripts/builder/secret-scan.py k8s/overlays/usecases/<name>        # plaintext credentials (CI gate)
poetry run python plugins/forjate/scripts/builder/scaffold-check.py k8s/overlays/usecases/<name>     # app/ against the records
poetry run python plugins/forjate/scripts/builder/tenant-drift.py <tenant-repo>                       # CLAUDE.md vs the tree
poetry run python plugins/forjate/skills/kustomize/scripts/assemble.py k8s/overlays/usecases/<name> [--target tenant --tenant-repo <dir>]
python3 scripts/gates/gates.py run <name> --transition 'crawl->walk'                                  # executes gates.yaml
poetry run pytest plugins/forjate/scripts/builder/tests
```

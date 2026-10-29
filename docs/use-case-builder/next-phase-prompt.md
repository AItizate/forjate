# Phase 5 — working agreement

Phase 5 is split into GitHub issues labelled `builder-p5`, one PR each against `main`. Every issue carries its own kick-off prompt, the model to run it with and its acceptance criteria. This file holds what every task shares, so the prompts only point at it.

Run a task in a fresh Claude Code session from the repo root (paste the issue's prompt), or delegate it from a coordinating session to an agent in a worktree. Long tasks (anything that runs eval batches) go to a fresh session.

## Orientation, for every task

Read `docs/use-case-builder/plan.md` (status line, §3 lessons, Phase 5) and the issue. Then read only what the issue names. `wiki/index.md` is the entry to the catalog; do not walk `k8s/**` by hand.

## Rules

- **Skills**: `SKILL.md` under 500 lines, pushy description, references split by stage or domain, the templated Context packs section verbatim (`skills/context-pack/references/section.md`). Agents preload the skill and `context-pack` and return only their record.
- **Evals**: judgement assertions beside the form checks; consistency assertions accept "agrees or asks" when two records can differ. When a with-skill assertion fails, read the record before touching the skill.
- **Running evals**: `./plugins/forjate/evals/run.sh <role> --model opus`; builders add `--max-turns 150 --timeout 5400`. Batches in series, one worktree per run, never two batches at once, `caffeinate -i -s` for the length of a batch. Delegate each batch to one subagent on Opus that only runs and reports (benchmark table, failed assertions with evidence, quality metrics, no transcripts). Copy the final `benchmark.md` to `docs/use-case-builder/benchmarks/<role>-<date>.md`.
- **After any change to `k8s/**`**: `poetry run python scripts/wiki-compile.py` and `scripts/wiki-lint.py`, and recompile once more after the commit.
- **Validation before a PR**: `poetry run pytest plugins/forjate/scripts/builder/tests` and `claude plugin validate ./plugins/forjate`.
- **Git**: branch `p5/<issue-number>-<slug>` from `main`, conventional commits, short, English. Push and open the PR only when asked; the PR closes its issue. Update the Phase 5 section of `plan.md` with the task's result in the same PR.

## Model guidance

| Work | Model | Why |
|------|-------|-----|
| Authoring skills and design decisions the skills depend on (role vocabulary, ADRs) | **Fable 5.1** | A skill is read on every future run, so the quality of its judgement compounds; the authoring tokens are a small share of the phase's cost. |
| Eval runs and batch subagents | **Opus** (`--model opus`, the runner's default) | Baselines must run on the same model as the with-skill configuration, and every benchmark since phase 0 is on Opus. Opus is also what runs the skills in production, so an eval on Opus proves a Fable-written skill works for its real reader. If a skill regresses after a rewrite, suspect instructions too terse for Opus first. |
| Builders, workloads, MCP server code | **Opus** | Concrete, verifiable output. |
| Mechanical tasks (CI runs, a catalog component, a release) | **Sonnet** | Low judgement, checked by CI. |
| Expert subagents in production | `model: inherit` | Until a benchmark shows a cheaper model holds the pass rate and the quality metrics; then `model: sonnet` per agent and re-run its evals. |

## Closing the phase

When every `builder-p5` issue is closed: tag `builder-p5`, update the status line and the Phase 5 section of `plan.md` with the results.

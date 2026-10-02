# Kick-off prompt for the next phase

Paste into a fresh Claude Code session from the repo root. Replace the phase number and the role list as the plan advances. Everything the session needs is in the repo; the prompt only points at it.

```
I am in ~/development/aitizate/forjate, branch feat/use-case-builder (PR #14; phases 0 and 1 done, tags builder-p0 and builder-p1).

Read, in this order: docs/use-case-builder/plan.md, docs/use-case-builder/contracts.md, plugins/forjate/README.md, plugins/forjate/evals/README.md, the two shared skills under plugins/forjate/skills/ (context-pack, kustomize) and one finished expert-style skill (stage-planner) with its agent in plugins/forjate/agents/.

Execute phase 2 of the plan: the core experts business, architecture, ai-engineering, data-store and data-pipeline. For each: a skill under plugins/forjate/skills/<role>/ (SKILL.md under 500 lines, pushy description, references/ split by stage or domain, the templated "Context packs" section pasted verbatim from skills/context-pack/references/section.md), a subagent in plugins/forjate/agents/<role>.md that preloads the skill and context-pack and returns only its Decision record, and an evals.json under plugins/forjate/evals/<role>/ with the three golden briefs (plugins/forjate/evals/fixtures/briefs/), one adversarial prompt, and one pack eval that forbids the expert's default choice. Assertions must include judgement checks (pack rule cited, open question raised, alternative rejected with reason), not only schema validity. Then add the cross-record consistency pass to plugins/forjate/scripts/builder/validate.py (incompatible component choices across records become an open question, never a silent fix) with pytest coverage, and wire the five experts into the coordinator's fan-out (business first, the rest in parallel).

Run the evals on Opus with ./plugins/forjate/evals/run.sh <role> --model opus. Run batches in series, never two batches at once, and never re-run a configuration while another run of the same eval is alive; one worktree per run. Before the first batch, add a per-run timeout to run.sh (a hung claude -p must be killed and recorded as is_error, not waited on). Delegate each batch to one subagent on Opus that only runs and reports: benchmark table, failed assertions with evidence, quality metrics; no transcripts. Grade with grade.py; copy the final benchmark.md of each skill to docs/use-case-builder/benchmarks/<role>-<date>.md.

Controlled commits per stage, conventional commits, short messages, English. Do not push until I ask. When phase 2 is complete, tag builder-p2, update the status line and the Phase 2 section of plan.md with the results, and tell me what to review.
```

## Model guidance

- **Authoring the skills**: the strongest model available. A skill is read on every future run, so the quality of its judgement compounds; the authoring tokens are a small share of the phase's cost.
- **Eval runs and batch subagents**: Opus (`--model opus`, the runner's default). Baselines must run on the same model as the with-skill configuration.
- **Expert subagents in production**: `model: inherit` until the benchmark shows a cheaper model holds the pass rate and the quality metrics; then set `model: sonnet` per agent and re-run its evals.

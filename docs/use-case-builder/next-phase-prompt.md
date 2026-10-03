# Kick-off prompt for the next phase

Paste into a fresh Claude Code session from the repo root. Replace the phase number and the role list as the plan advances. Everything the session needs is in the repo; the prompt only points at it.

```
I am in ~/development/aitizate/forjate, branch feat/use-case-builder (PR #14; phases 0 to 2 done, tags builder-p0, builder-p1 and builder-p2).

Read, in this order: docs/use-case-builder/plan.md, docs/use-case-builder/contracts.md, plugins/forjate/README.md, plugins/forjate/evals/README.md, docs/use-case-builder/experts.md, the two shared skills under plugins/forjate/skills/ (context-pack, kustomize) and one finished expert (data-store) with its agent in plugins/forjate/agents/ and its evals in plugins/forjate/evals/data-store/.

Execute phase 3 of the plan: the governance experts security, compliance, quality and devops, plus executable gates (gates.yaml consolidation by quality). For each: a skill under plugins/forjate/skills/<role>/ (SKILL.md under 500 lines, pushy description, references/ split by stage or domain, the templated "Context packs" section pasted verbatim from skills/context-pack/references/section.md), a subagent in plugins/forjate/agents/<role>.md that preloads the skill and context-pack and returns only its Decision record, and an evals.json under plugins/forjate/evals/<role>/ with the three golden briefs (plugins/forjate/evals/fixtures/briefs/), one adversarial prompt, and one pack eval that forbids the expert's default choice. Assertions must include judgement checks (pack rule cited, open question raised, alternative rejected with reason), not only schema validity. Then extend validate.py check 6 with the groups these experts can conflict on (psa_level, secrets_mechanism are already shared settings) with pytest coverage, and wire the four experts into the coordinator's wave 2 and the gates consolidation after it.

Run the evals on Opus with ./plugins/forjate/evals/run.sh <role> --model opus. Run batches in series, never two batches at once, and never re-run a configuration while another run of the same eval is alive; one worktree per run. Keep the machine awake for the batches (caffeinate -i -s); run.sh already kills a hung claude -p on a wall-clock deadline and records it as is_error. Delegate each batch to one subagent on Opus that only runs and reports: benchmark table, failed assertions with evidence, quality metrics; no transcripts. Grade with grade.py; copy the final benchmark.md of each skill to docs/use-case-builder/benchmarks/<role>-<date>.md.

Controlled commits per stage, conventional commits, short messages, English. Do not push until I ask. When phase 3 is complete, tag builder-p3, update the status line and the Phase 2 section of plan.md with the results, and tell me what to review.
```

## Model guidance

- **Authoring the skills**: the strongest model available. A skill is read on every future run, so the quality of its judgement compounds; the authoring tokens are a small share of the phase's cost.
- **Eval runs and batch subagents**: Opus (`--model opus`, the runner's default). Baselines must run on the same model as the with-skill configuration.
- **Expert subagents in production**: `model: inherit` until the benchmark shows a cheaper model holds the pass rate and the quality metrics; then set `model: sonnet` per agent and re-run its evals.

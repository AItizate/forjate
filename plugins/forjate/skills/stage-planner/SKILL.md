---
name: stage-planner
description: Turns a use-case brief into a Crawl / Walk / Run stage plan for Forjate — which stages are in scope, what each one has to prove, observable exit criteria, cost envelope per stage, and which expert roles need to run. Use it whenever a brief.yaml exists and no stage-plan.yaml does, whenever someone asks "how do we get this from PoC to production", wants phases, milestones, a roadmap for an automation, or asks which experts or decisions a use case needs. Also use it to re-plan after a brief changes.
user-invocable: true
argument-hint: "<usecase-dir>"
allowed-tools: Read Grep Glob Write Bash(poetry run python *) Bash(python3 *) Bash(cat *)
---

# Stage planner

You turn `.builder/brief.yaml` into `.builder/stage-plan.yaml`. The plan is the contract every expert works against: it says which stages exist for this use case, what each one must prove before the next unlocks, and which experts are worth running. A good plan is small, observable, and honest about what is out of scope.

Schema: `${CLAUDE_PLUGIN_ROOT}/scripts/builder/schemas/stage-plan.schema.json`. Stage defaults and cost figures: `references/stage-defaults.md`. Which experts to run or skip: `references/expert-selection.md`. Read both before planning; they are short.

## Procedure

1. Read `brief.yaml`. Note `data.classification`, `constraints.regulated`, `constraints.budget_per_month_usd`, `stages_requested`, `success.metric` and `language`. Write the plan in that language. If the use case already ships a `usecase.yaml`, read `spec.jobs`: the Crawl `verify-job` gate must name that verify Job, not a hypothetical one.
2. Resolve context packs for your role (section below). Packs can forbid a stage's defaults or cap cost; they shape the plan before you write it.
3. Decide the stages. Crawl is always in scope: nothing is planned that has not been proven on a disposable cluster first. Walk and Run are in scope only when the brief says real users or production are wanted, or when `stages_requested` includes them. Mark everything else `in_scope: false` with a `skip_reason` in one sentence. A one-off migration stops at Walk; a nightly internal report may stop at Crawl.
4. For each stage in scope write a `goal` (one sentence, what it proves), the `forjate_tier`, `exit_criteria` and `estimated_cost_usd_month` from the defaults.
5. Select experts. Every role in `references/expert-selection.md` gets an entry with `run: true` or a `skip_reason`. `business` always runs. Skipping is a decision, not an omission.
6. Write the file, then validate:

   ```bash
   poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/validate.py <usecase-dir>
   ```

   Fix every error. Warnings about missing decision records are expected at this point.
7. Reply with the path and a five-line summary: stages in scope, the Crawl goal, the first gate, the cost envelope, the experts skipped and why.

## Exit criteria that an agent can check

An exit criterion is a gate: `{ id, text, owner, check }`. The `check` says how it is verified: `verify-job` (a Job in the overlay exits 0), `ci` (a workflow passes), `metric` (a measurable number), or `manual` (a named human signs). Prefer the first three. "Stakeholders are happy" is not a gate; "the approver named in the brief signs the Walk report" is.

A manual gate is a meeting; an automated gate is a proof. Keep manual gates to the approver's sign-off and the decisions only a person can make (retention, budget), and express everything else as `verify-job`, `ci` or `metric`, even when the check does not exist yet: naming it is what makes the quality expert build it. If more than a third of a transition's gates are manual, rewrite them.

Crawl always carries at least one `verify-job` gate because the ephemeral runner blocks on it: `ephemeral.sh up <name>` returning 0 is the proof that Crawl works. Walk carries at least one `metric` gate tied to the brief's success metric. Run carries the compliance and operability gates the regulated flag demands.

Gate ids follow `G-<AREA>-<n>`: `G-Q-1` for quality, `G-SEC-1` for security, `G-BIZ-1` for business, `G-OPS-1` for devops. Keep the numbering per area; the quality expert consolidates them later into `gates.yaml`.

## Judgement calls

- **Regulated or `pii`/`financial`/`health` data**: Run must list a PSA `restricted` gate, an egress gate, and compliance sign-off. Walk must list network isolation. Do not soften these to fit a budget; raise the cost instead and let the business expert argue.
- **Budget below the stage default**: keep the stage in scope, set the cost to the default anyway, and add an `out_of_scope` line saying what would have to give. The plan reports reality; the business expert negotiates it.
- **No model in the loop** (deterministic ETL, CDC, migrations): skip `ai-engineering`, say so.
- **No human-facing surface** (batch, operator-only): skip `ux`, say so.
- **Vague brief**: do not plan around the gap. Put the question in the plan's Crawl `out_of_scope` list prefixed with `OPEN:` and plan the rest; the coordinator will route it to the user.

## Context packs

Before reasoning about the use case, resolve the packs that apply to you:

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/packs.py resolve --for stage-planner --usecase-dir <usecase-dir>
```

Treat `must` entries as hard constraints: never decide against one, and if the use case cannot be served within it, raise an `open_questions` entry with `caused_by_rule` instead of bending the rule. Treat `should` entries as the default, deviating only with an explicit reason in `rationale`. Mention `may` entries when relevant. Cite every ref that shaped a stage decision in that stage's `constrained_by`. Open a guideline file only when its summary matters to the decision at hand. If the resolver reports an override of a `must`, say so in your record so it lands in `gates.yaml`. With no packs active, the factory defaults apply and your rationale says so.

Full rules: `forjate:context-pack`. The stage plan has no `constrained_by` field; cite pack refs inside the affected gate's `text` instead, e.g. "PSA restricted (pack:regulated-corp#SEC-1)".

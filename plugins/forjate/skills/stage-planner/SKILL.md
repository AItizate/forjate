---
name: stage-planner
description: Turns a use-case brief into a Crawl / Walk / Run stage plan for Forjate — which stages are in scope, what each one has to prove, the autonomy ceiling the agent may reach at each stage, observable exit criteria including security in week one, cost envelope per stage, and which expert roles need to run. Use it whenever a brief.yaml exists and no stage-plan.yaml does, whenever someone asks "how do we get this from PoC to production", wants phases, milestones, a roadmap for an automation, or asks which experts or decisions a use case needs. Also use it to re-plan after a brief changes.
user-invocable: true
argument-hint: "<usecase-dir>"
allowed-tools: Read Grep Glob Write Bash(poetry run python *) Bash(python3 *) Bash(cat *)
---

# Stage planner

You turn `.builder/brief.yaml` into `.builder/stage-plan.yaml`. The plan is the contract every expert works against: it says which stages exist for this use case, what each one must prove before the next unlocks, and which experts are worth running. A good plan is small, observable, and honest about what is out of scope.

Schema: `${CLAUDE_PLUGIN_ROOT}/scripts/builder/schemas/stage-plan.schema.json`. Stage defaults and cost figures: `references/stage-defaults.md`. Which experts to run or skip: `references/expert-selection.md`. Read both before planning; they are short.

## Procedure

1. Read `brief.yaml`. Note `data.classification`, `constraints.regulated`, `constraints.budget_per_month_usd`, `stages_requested`, `success.metric`, `autonomy`, `risk_profile`, `isolation` and `language`. Write the plan in that language. If the use case already ships a `usecase.yaml`, read `spec.jobs`: the Crawl `verify-job` gate must name that verify Job, not a hypothetical one.
2. Resolve context packs for your role (section below). Packs can forbid a stage's defaults or cap cost; they shape the plan before you write it.
3. Decide the stages. Crawl is always in scope: nothing is planned that has not been proven on a disposable cluster first. Walk and Run are in scope only when the brief says real users or production are wanted, or when `stages_requested` includes them. Mark everything else `in_scope: false` with a `skip_reason` in one sentence. A one-off migration stops at Walk; a nightly internal report may stop at Crawl.
4. For each stage in scope write a `goal` (one sentence, what it proves), the `forjate_tier`, the `autonomy` ceiling (posture below), `exit_criteria` and `estimated_cost_usd_month` from the defaults. Crawl's exit criteria include the security gate of week one (`G-SEC-1`: the sandbox and the access grants approved by the organisation's security owner, `manual`, owner `security`) whenever the use case touches data above `internal`, writes to a system of record, exposes a surface, or carries a `risk_profile`; the brief's `isolation` is noted in the Walk goal when it is `logical` or `physical`.
5. Select experts. Every role in `references/expert-selection.md` gets an entry with `run: true` or a `skip_reason`. `business` always runs. Skipping is a decision, not an omission.
6. Write the file, then validate:

   ```bash
   poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/validate.py <usecase-dir>
   ```

   Fix every error. Warnings about missing decision records are expected at this point.
7. Reply with the path and a five-line summary: stages in scope, the Crawl goal, the first gate, the cost envelope, the experts skipped and why.

## Governance posture

| key | values | default Crawl → Walk → Run | owner |
|-----|--------|-----------------------------|-------|
| `autonomy` (per stage, `stages.<s>.autonomy`) | `assistive` / `semi-autonomous` / `autonomous` | `assistive` → `semi-autonomous` at most → the brief's `autonomy` at most, `autonomous` only with a `risk_profile` the gates cover | you; ai-engineering, ux and quality copy it into their records |

- **Autonomy is a ceiling per stage, never a default.** Crawl is `assistive`: the agent recommends and a person acts, because a PoC proves the reasoning, not the right to act. Walk is at most `semi-autonomous`: registered tools, writes behind approval, accuracy measured on a golden set. Run reaches the brief's `autonomy` only when the Walk evidence supports it, action by action, starting read-only; each increase is a gate with an owner (`G-AUT-<n>`, `manual`, the approver named), and `gates.yaml` is where it is recorded. A brief that asks for `autonomous` gets the ceiling it has earned and the gates that would raise it, not the autonomy; the validator rejects a plan whose Crawl is not `assistive` or whose stage exceeds the brief.
- **The risk profile lowers the ceiling and adds gates.** `regulated-decision` or `irreversible-action` keeps Run at `semi-autonomous` until a named gate per action says otherwise and makes the compliance sign-off a Run exit criterion; `high-impact-action` adds a kill-switch rehearsal gate at Run; `vulnerable-population` and `customer-facing` make `ux` mandatory and add the disclosure and the review-that-validates to Walk's criteria. Write the reason next to the ceiling in the stage's `goal` or `out_of_scope`, so the experts inherit it.
- **Security is in week one, not at the end.** Infosec approval before the first deployment is one of the three places adoption dies; the Crawl exit criteria carry the sandbox and access gate, and the `security` expert runs at Crawl for anything with data above `internal`, a write, a surface or a `risk_profile`. A plan that meets security at Walk has planned the delay.

## Exit criteria that an agent can check

An exit criterion is a gate: `{ id, text, owner, check }`. The `check` says how it is verified: `verify-job` (a Job in the overlay exits 0), `ci` (a workflow passes), `metric` (a measurable number), or `manual` (a named human signs). Prefer the first three. "Stakeholders are happy" is not a gate; "the approver named in the brief signs the Walk report" is.

A manual gate is a meeting; an automated gate is a proof. Keep manual gates to the approver's sign-off and the decisions only a person can make (retention, budget), and express everything else as `verify-job`, `ci` or `metric`, even when the check does not exist yet: naming it is what makes the quality expert build it. If more than a third of a transition's gates are manual, rewrite them.

Crawl always carries at least one `verify-job` gate because the ephemeral runner blocks on it: `ephemeral.sh up <name>` returning 0 is the proof that Crawl works. Walk carries at least one `metric` gate tied to the brief's success metric. Run carries the compliance and operability gates the regulated flag demands.

Gate ids follow `G-<AREA>-<n>`: `G-Q-1` for quality, `G-SEC-1` for security, `G-BIZ-1` for business, `G-OPS-1` for devops. Keep the numbering per area; the quality expert consolidates them later into `gates.yaml`.

## Judgement calls

- **Regulated or `pii`/`financial`/`health` data**: Run must list a PSA `restricted` gate, an egress gate, and compliance sign-off. Walk must list network isolation. Crawl lists the security week-one gate. Do not soften these to fit a budget; raise the cost instead and let the business expert argue.
- **Budget below the stage default**: keep the stage in scope, set the cost to the default anyway, and add an `out_of_scope` line saying what would have to give. The plan reports reality; the business expert negotiates it.
- **No model in the loop** (deterministic ETL, CDC, migrations): skip `ai-engineering`, say so.
- **No human-facing surface** (batch, operator-only): skip `ux`, say so; never when `risk_profile` includes `customer-facing` or `vulnerable-population`.
- **Vague brief**: do not plan around the gap. Put the question in the plan's Crawl `out_of_scope` list prefixed with `OPEN:` and plan the rest; the coordinator will route it to the user.

## Context packs

Before reasoning about the use case, resolve the packs that apply to you:

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/packs.py resolve --for stage-planner --usecase-dir <usecase-dir>
```

Treat `must` entries as hard constraints: never decide against one, and if the use case cannot be served within it, raise an `open_questions` entry with `caused_by_rule` instead of bending the rule. Treat `should` entries as the default, deviating only with an explicit reason in `rationale`. Mention `may` entries when relevant. Cite every ref that shaped a stage decision in that stage's `constrained_by`. Open a guideline file only when its summary matters to the decision at hand. If the resolver reports an override of a `must`, say so in your record so it lands in `gates.yaml`. With no packs active, the factory defaults apply and your rationale says so.

Full rules: `forjate:context-pack`. For you the rules that matter are `require_setting` on `autonomy` (an organisation that pins Crawl to `assistive`, which is the factory default anyway), cost caps, and an operating-model guideline whose calendar maps to the stages. The stage plan has no `constrained_by` field; cite pack refs inside the affected gate's `text` instead, e.g. "PSA restricted (pack:regulated-corp#SEC-1)".

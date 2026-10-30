# Review report template

Printed by `review`, and at the end of `build`/`resume`. Written in `brief.spec.language`. Every section reads from a file; a missing file yields "not yet produced", never a guess.

```
# <name> — use-case review

**Problem** <brief.spec.problem, one paragraph>
**Success metric** <metric> (baseline <b>, target <t>)
**Data** <classification>, residency <r or unconstrained> · **Regulated** <yes/no>
**Packs** <names or none>

## Stages
| Stage | In scope | Goal | Tier | Cost USD/mo | Gates |
one row per stage; skipped stages show the skip reason in Goal

## Decisions
one block per decisions/*.yaml:
### <area>
- Crawl: <choice list> — <first sentence of rationale>
- Walk: …
- Run: …
- Risks: <ids and one-liners>
- Constrained by: <pack refs>

## Posture
| Stage | Autonomy (plan) | Writes | Intent validation | Kill switch | Audit artifacts |
one row per stage in scope, from stage-plan.yaml `autonomy` and the ai-engineering, security and quality records; a cell reads "not yet produced" when its record is missing
Operating model: <business `operating_model`; RACI lines; the three adoption frictions with their owners; devops `severities` when present; `open_standards` with its exceptions>
Review: <ux `review_mode` and `review_independence` per checkpoint; `control_levels` per persona; `disclosure` lines>

## Open questions
<every open_questions entry across records, with the area and the blocking stage; a question caused by a pack rule shows the rule ref>
Conflicts between experts: <every `cross-record conflict` line validate.py reported, each with the open question that acknowledges it, or "none">

## Gates (consolidated)
<from gates.yaml when present; otherwise "quality expert has not consolidated yet", followed by the gate_to_next lists found in the records>
| Transition | Approver | Gates | Automated (verify-job / ci / metric) | Manual |
one row per transition; counts from check.type, absent check counts as manual
then one line per gate: `<id> [<check.type>: <ref>] <text> (<owner>)`, manual ones last
Pack overrides: <from gates.yaml, or none>

## Assembly
<from usecase.yaml, kustomization.yaml, stages/* and .builder/scaffold.yaml when present; otherwise "not assembled yet">
- Workload: <scaffold package and image, workloads with their commands, tools with their flags; tests and scaffold-check result when known>
- Overlay: <root and stages that build, kubeconform result, the gates.py ci table for crawl->walk when run>
- Assembly notes: <every note the generator printed: surfaces the scaffold does not ship yet, guessed secret keys, matrices to write by hand>
- Crawl proof: <ephemeral.sh up result and the KPI/EVAL lines from the verify Job, or "not run">

## Tenant drift
<only inside a tenant repo: the four lists tenant-drift.py prints; otherwise omit the section>

## Not yet available
<expert roles the plan runs but that produced no record, with the reason: no agent yet, or failed>

## Log
<last five lines of log.md>
```

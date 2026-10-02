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

## Open questions
<every open_questions entry across records, with the area and the blocking stage; a question caused by a pack rule shows the rule ref>
Conflicts between experts: <every `cross-record conflict` line validate.py reported, each with the open question that acknowledges it, or "none">

## Gates (consolidated)
<from gates.yaml when present; otherwise "quality expert has not consolidated yet", followed by the gate_to_next lists found in the records>
Pack overrides: <from gates.yaml, or none>

## Not yet available
<expert roles the plan runs but that produced no record, with the reason: no agent yet, or failed>

## Log
<last five lines of log.md>
```

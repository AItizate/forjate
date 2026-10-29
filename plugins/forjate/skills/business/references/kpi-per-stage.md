# KPI per stage

One metric, three targets. The quality expert turns `kpi_metric` into a metric query and a gate; if the name changes between stages the gate chain breaks.

| Stage | Dataset | Window | Target shape | Gate |
|-------|---------|--------|--------------|------|
| Crawl | seeded, real-shaped, small (tens to hundreds of items) | one run | a fraction of the brief's target, **zero** on the error dimension | `G-BIZ-1` metric measured once and seen by the approver |
| Walk | real traffic, real users, internal | the brief's window or 30 days | the brief's target | `G-BIZ-2` metric over the window plus `manual` sign-off |
| Run | all traffic | rolling 90 days | the brief's target sustained, with evidence per item when regulated | `G-BIZ-3` metric sustained plus sign-off |

## Shapes that work

- `straight_through_rate`: share of items handled with no human touch. Pair with an error dimension (`wrong_amounts: 0`).
- `resolved_without_human_rate`: share of conversations closed by the agent, with `escalations_with_full_context: 100%` as the guard-rail.
- `rows_migrated_and_verified`: count plus `mismatches_on_sample: 0`.
- `cycle_time_hours`: when the value is speed, not labour; always with a volume floor so a fast empty pipeline does not pass.

## Shapes that fail

- "User satisfaction" with no instrument: the UX expert can add Formbricks at Walk; until then it is not a KPI.
- "Accuracy" without a labelled set: say who labels and how many; that is a Crawl gate, not a number.
- Two KPIs: the second one becomes a `risks` entry or a gate, never a second `kpi_metric`.
- A target with no window: "80%" means nothing; "80% over 30 days of real invoices" is a gate.

## Baseline rules

The baseline is what the brief says or `unknown`. `unknown` adds an open question with `blocks_stage: walk`: who measures the current number, on what sample, by when. Crawl can run without it; Walk cannot claim improvement without it.

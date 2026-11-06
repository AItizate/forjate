# Benchmark — coordinator-e2e / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| cold-start-quote-drafting | with_skill | 96% | 116 | 33.824 | 6 | opus-5-5 |

**with_skill** mean pass rate: 96% over 1 run(s)

Iteration 2 predates `wall_seconds` in `timing.json`: its 116 s is the last turn's API time. The run took about 61 min of wall clock, and `ephemeral.sh up` took 119 s.

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| cold-start-quote-drafting | with_skill | 10 | 59 | 0 | 0 | 82 | 83 | 72 | 52 |

## Cost per agent (agent-costs.py: the run's cost split by price-weighted tokens)

| eval | config | agent | calls | share | cost USD |
|---|---|---|---|---|---|
| cold-start-quote-drafting | with_skill | forjate:app-scaffold | 1 | 35.8% | 12.1 |
| cold-start-quote-drafting | with_skill | forjate:quality | 5 | 14.1% | 4.75 |
| cold-start-quote-drafting | with_skill | main | 1 | 8.1% | 2.72 |
| cold-start-quote-drafting | with_skill | forjate:kustomize | 1 | 7.8% | 2.63 |
| cold-start-quote-drafting | with_skill | forjate:security | 1 | 6.8% | 2.31 |
| cold-start-quote-drafting | with_skill | forjate:ux | 2 | 4.5% | 1.54 |
| cold-start-quote-drafting | with_skill | forjate:ai-engineering | 1 | 4.3% | 1.46 |
| cold-start-quote-drafting | with_skill | forjate:devops | 1 | 4.0% | 1.37 |
| cold-start-quote-drafting | with_skill | forjate:compliance | 2 | 3.9% | 1.31 |
| cold-start-quote-drafting | with_skill | forjate:architecture | 2 | 3.5% | 1.2 |
| cold-start-quote-drafting | with_skill | forjate:data-pipeline | 2 | 2.5% | 0.86 |
| cold-start-quote-drafting | with_skill | forjate:data-store | 1 | 2.0% | 0.67 |
| cold-start-quote-drafting | with_skill | forjate:business | 1 | 1.5% | 0.52 |
| cold-start-quote-drafting | with_skill | forjate:stage-planner | 1 | 1.1% | 0.38 |

# Benchmark — coordinator-e2e / iteration-4

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| cold-start-invoice-intake | with_skill | 100% | 7193 | 120.79 | 26 | opus-5-5 |

**with_skill** mean pass rate: 100% over 1 run(s)

Two segments: `claude -p` killed the background builders 10 min after the last turn, and `run.sh --resume` continued the same session. Seconds, cost and turns are the sum of both. `ephemeral.sh up` took 177 s.

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| cold-start-invoice-intake | with_skill | 10 | 90 | 23 | 52 | 131 | 152 | 157 | 97 |

## Cost per agent (agent-costs.py: the run's cost split by price-weighted tokens)

| eval | config | agent | calls | share | cost USD |
|---|---|---|---|---|---|
| cold-start-invoice-intake | with_skill | forjate:app-scaffold | 1 | 15.6% | 18.83 |
| cold-start-invoice-intake | with_skill | forjate:quality | 2 | 9.6% | 11.57 |
| cold-start-invoice-intake | with_skill | forjate:devops | 1 | 9.2% | 11.08 |
| cold-start-invoice-intake | with_skill | forjate:architecture | 1 | 8.5% | 10.27 |
| cold-start-invoice-intake | with_skill | forjate:compliance | 1 | 8.3% | 10.06 |
| cold-start-invoice-intake | with_skill | forjate:ux | 1 | 8.0% | 9.64 |
| cold-start-invoice-intake | with_skill | main | 1 | 7.4% | 8.96 |
| cold-start-invoice-intake | with_skill | forjate:kustomize | 1 | 7.3% | 8.87 |
| cold-start-invoice-intake | with_skill | forjate:data-pipeline | 1 | 6.6% | 7.95 |
| cold-start-invoice-intake | with_skill | forjate:security | 1 | 6.5% | 7.9 |
| cold-start-invoice-intake | with_skill | forjate:ai-engineering | 1 | 5.5% | 6.7 |
| cold-start-invoice-intake | with_skill | forjate:data-store | 1 | 5.0% | 6.01 |
| cold-start-invoice-intake | with_skill | forjate:business | 1 | 1.3% | 1.62 |
| cold-start-invoice-intake | with_skill | forjate:stage-planner | 1 | 1.1% | 1.33 |

Every cold start of #28, measured from `result.json`: quote-drafting 26.92 (iteration 1) and 33.82 USD (iteration 2), invoice-intake 11.14 (iteration 3, cut by the usage limit) and 120.79 USD (iteration 4, resumed): 192.67 USD.

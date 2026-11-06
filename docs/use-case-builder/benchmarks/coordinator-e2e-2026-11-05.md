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

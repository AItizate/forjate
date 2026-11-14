# Benchmark — kustomize / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 100% | 135 | 0.863 | 35 | opus-5-5 |
| add-redis-to-usecase | without_skill | 100% | 105 | 0.632 | 34 | opus-5-5 |
| assemble-invoice-intake | with_skill | 100% | 259 | 1.003 | 31 | opus-5-5 |
| assemble-invoice-intake | without_skill | 33% | 346 | 2.882 | 41 | ERROR: is_error |
| component-list-to-crawl-overlay | with_skill | 100% | 226 | 1.355 | 42 | opus-5-5 |
| component-list-to-crawl-overlay | without_skill | 100% | 271 | 1.594 | 49 | opus-5-5 |
| pack-constrained-stage-overlay | with_skill | 100% | 210 | 1.269 | 39 | opus-5-5 |
| pack-constrained-stage-overlay | without_skill | 100% | 225 | 1.24 | 59 | opus-5-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

**without_skill** mean pass rate: 83% over 4 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| add-redis-to-usecase | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| assemble-invoice-intake | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| assemble-invoice-intake | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| component-list-to-crawl-overlay | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| component-list-to-crawl-overlay | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pack-constrained-stage-overlay | with_skill | 1 | 1 | 1 | 2 | 1 | 0 | 1 | 0 |
| pack-constrained-stage-overlay | without_skill | 1 | 1 | 1 | 2 | 1 | 0 | 1 | 0 |

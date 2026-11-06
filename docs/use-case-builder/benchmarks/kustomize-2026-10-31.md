# Benchmark — kustomize / iteration-4

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 100% | 114 | 0.744 | 29 | opus-5-5 |
| add-redis-to-usecase | without_skill | 100% | 111 | 0.86 | 37 | opus-5-5 |
| assemble-invoice-intake | with_skill | 100% | 883 | 2.793 | 104 | opus-5-5 |
| assemble-invoice-intake | without_skill | 94% | 2172 | 11.363 | 239 | opus-5-5 |
| component-list-to-crawl-overlay | with_skill | 100% | 263 | 1.58 | 45 | opus-5-5 |
| component-list-to-crawl-overlay | without_skill | 100% | 272 | 1.709 | 56 | opus-5-5 |
| pack-constrained-stage-overlay | with_skill | 100% | 239 | 1.683 | 61 | opus-5-5 |
| pack-constrained-stage-overlay | without_skill | 100% | 264 | 1.472 | 55 | opus-5-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

**without_skill** mean pass rate: 99% over 4 run(s)

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

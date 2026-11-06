# Benchmark — kustomize / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 100% | 135 | 0.896 | 40 | opus-5-5 |
| assemble-invoice-intake | with_skill | 100% | 1186 | 4.293 | 144 | opus-5-5 |
| component-list-to-crawl-overlay | with_skill | 100% | 255 | 1.675 | 80 | opus-5-5 |
| pack-constrained-stage-overlay | with_skill | 100% | 226 | 1.389 | 64 | opus-5-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| assemble-invoice-intake | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| component-list-to-crawl-overlay | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pack-constrained-stage-overlay | with_skill | 1 | 1 | 1 | 2 | 1 | 0 | 1 | 0 |

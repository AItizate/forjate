# Benchmark — kustomize / iteration-3

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| add-redis-to-usecase | with_skill | 100% | 209 | 2.133 | 48 | haiku-4-5-20251001,opus-5 |
| add-redis-to-usecase | without_skill | 100% | 106 | 1.071 | 31 | haiku-4-5-20251001,opus-5 |
| assemble-invoice-intake | with_skill | 100% | 935 | 7.928 | 116 | haiku-4-5-20251001,opus-5 |
| assemble-invoice-intake | without_skill | 89% | 1655 | 18.086 | 151 | ERROR: is_error |
| component-list-to-crawl-overlay | with_skill | 100% | 469 | 4.943 | 80 | haiku-4-5-20251001,opus-5 |
| component-list-to-crawl-overlay | without_skill | 100% | 455 | 4.663 | 71 | haiku-4-5-20251001,opus-5 |
| pack-constrained-stage-overlay | with_skill | 100% | 221 | 2.199 | 55 | haiku-4-5-20251001,opus-5 |
| pack-constrained-stage-overlay | without_skill | 100% | 186 | 1.567 | 32 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

**without_skill** mean pass rate: 97% over 4 run(s)

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

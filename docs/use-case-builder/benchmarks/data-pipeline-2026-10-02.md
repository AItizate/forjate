# Benchmark — data-pipeline / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-cdc-at-crawl | with_skill | 86% | 255 | 1.542 | 28 | haiku-4-5-20251001,opus-5 |
| adversarial-cdc-at-crawl | without_skill | 71% | 256 | 1.68 | 28 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | with_skill | 100% | 238 | 1.357 | 29 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | without_skill | 55% | 184 | 1.351 | 27 | haiku-4-5-20251001,opus-5 |
| migration-regulated | with_skill | 100% | 216 | 1.277 | 24 | haiku-4-5-20251001,opus-5 |
| migration-regulated | without_skill | 58% | 210 | 1.37 | 27 | haiku-4-5-20251001,opus-5 |
| pack-no-docling | with_skill | 100% | 210 | 1.409 | 27 | haiku-4-5-20251001,opus-5 |
| pack-no-docling | without_skill | 100% | 249 | 1.497 | 22 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 227 | 1.305 | 22 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 53% | 281 | 1.69 | 30 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 97% over 5 run(s)

**without_skill** mean pass rate: 68% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-cdc-at-crawl | with_skill | 2 | 4 | 0 | 1 | 6 | 6 | 5 | 4 |
| adversarial-cdc-at-crawl | without_skill | 2 | 3 | 1 | 4 | 5 | 9 | 6 | 5 |
| chat-copilot-no-packs | with_skill | 2 | 4 | 0 | 0 | 8 | 6 | 7 | 6 |
| chat-copilot-no-packs | without_skill | 2 | 4 | 0 | 0 | 7 | 6 | 4 | 3 |
| migration-regulated | with_skill | 2 | 3 | 2 | 2 | 5 | 5 | 5 | 4 |
| migration-regulated | without_skill | 2 | 3 | 2 | 2 | 7 | 6 | 4 | 4 |
| pack-no-docling | with_skill | 2 | 4 | 2 | 5 | 8 | 7 | 9 | 6 |
| pack-no-docling | without_skill | 2 | 5 | 2 | 5 | 10 | 8 | 8 | 6 |
| regulated-invoice-intake | with_skill | 2 | 4 | 0 | 2 | 10 | 10 | 5 | 4 |
| regulated-invoice-intake | without_skill | 2 | 5 | 0 | 1 | 8 | 8 | 6 | 5 |

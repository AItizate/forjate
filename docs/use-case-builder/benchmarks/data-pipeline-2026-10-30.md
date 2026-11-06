# Benchmark — data-pipeline / iteration-3

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-cdc-at-crawl | with_skill | 100% | 186 | 0.886 | 16 | opus-5-5 |
| adversarial-cdc-at-crawl | without_skill | 86% | 140 | 0.934 | 15 | opus-5-5 |
| chat-copilot-no-packs | with_skill | 100% | 127 | 0.797 | 17 | opus-5-5 |
| chat-copilot-no-packs | without_skill | 55% | 156 | 0.995 | 16 | opus-5-5 |
| migration-regulated | with_skill | 100% | 173 | 0.996 | 24 | opus-5-5 |
| migration-regulated | without_skill | 67% | 136 | 1.024 | 19 | opus-5-5 |
| pack-no-docling | with_skill | 100% | 148 | 0.965 | 20 | opus-5-5 |
| pack-no-docling | without_skill | 89% | 134 | 0.981 | 18 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 207 | 1.019 | 19 | opus-5-5 |
| regulated-invoice-intake | without_skill | 50% | 172 | 1.176 | 21 | opus-5-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 69% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-cdc-at-crawl | with_skill | 1 | 3 | 0 | 2 | 8 | 6 | 6 | 5 |
| adversarial-cdc-at-crawl | without_skill | 1 | 3 | 1 | 5 | 5 | 7 | 2 | 1 |
| chat-copilot-no-packs | with_skill | 1 | 4 | 0 | 0 | 6 | 6 | 4 | 4 |
| chat-copilot-no-packs | without_skill | 1 | 3 | 0 | 0 | 8 | 6 | 4 | 4 |
| migration-regulated | with_skill | 1 | 4 | 1 | 2 | 6 | 7 | 5 | 5 |
| migration-regulated | without_skill | 1 | 4 | 1 | 6 | 4 | 5 | 4 | 3 |
| pack-no-docling | with_skill | 1 | 3 | 2 | 5 | 8 | 7 | 4 | 4 |
| pack-no-docling | without_skill | 1 | 3 | 2 | 5 | 8 | 7 | 4 | 3 |
| regulated-invoice-intake | with_skill | 1 | 4 | 1 | 2 | 9 | 10 | 5 | 4 |
| regulated-invoice-intake | without_skill | 1 | 5 | 2 | 10 | 11 | 8 | 3 | 3 |

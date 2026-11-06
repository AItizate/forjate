# Benchmark — architecture / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-single-container | with_skill | 100% | 236 | 1.233 | 19 | opus-5-5 |
| adversarial-single-container | without_skill | 71% | 234 | 1.209 | 19 | opus-5-5 |
| chat-copilot-no-packs | with_skill | 100% | 213 | 1.136 | 25 | opus-5-5 |
| chat-copilot-no-packs | without_skill | 82% | 115 | 0.894 | 13 | opus-5-5 |
| migration-regulated | with_skill | 100% | 218 | 1.238 | 26 | opus-5-5 |
| migration-regulated | without_skill | 100% | 108 | 0.748 | 16 | opus-5-5 |
| pack-no-temporal | with_skill | 100% | 155 | 1.08 | 23 | opus-5-5 |
| pack-no-temporal | without_skill | 100% | 157 | 1.213 | 24 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 191 | 1.217 | 26 | opus-5-5 |
| regulated-invoice-intake | without_skill | 60% | 226 | 1.356 | 18 | opus-5-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 83% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-single-container | with_skill | 1 | 3 | 0 | 2 | 10 | 7 | 5 | 4 |
| adversarial-single-container | without_skill | 1 | 5 | 0 | 3 | 12 | 7 | 5 | 4 |
| chat-copilot-no-packs | with_skill | 1 | 3 | 0 | 0 | 6 | 5 | 5 | 5 |
| chat-copilot-no-packs | without_skill | 1 | 3 | 0 | 0 | 8 | 5 | 2 | 2 |
| migration-regulated | with_skill | 1 | 3 | 1 | 2 | 6 | 6 | 4 | 4 |
| migration-regulated | without_skill | 1 | 2 | 1 | 2 | 6 | 5 | 2 | 1 |
| pack-no-temporal | with_skill | 1 | 3 | 1 | 4 | 7 | 6 | 5 | 5 |
| pack-no-temporal | without_skill | 1 | 2 | 1 | 3 | 8 | 5 | 3 | 2 |
| regulated-invoice-intake | with_skill | 1 | 4 | 0 | 2 | 9 | 8 | 4 | 4 |
| regulated-invoice-intake | without_skill | 1 | 4 | 0 | 12 | 11 | 10 | 3 | 2 |

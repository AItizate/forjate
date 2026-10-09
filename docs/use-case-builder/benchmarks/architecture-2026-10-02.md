# Benchmark — architecture / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-single-container | with_skill | 100% | 246 | 1.363 | 25 | haiku-4-5-20251001,opus-5 |
| adversarial-single-container | without_skill | 71% | 770 | 1.463 | 26 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | with_skill | 100% | 248 | 1.396 | 24 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | without_skill | 73% | 206 | 1.493 | 27 | haiku-4-5-20251001,opus-5 |
| migration-regulated | with_skill | 100% | 256 | 1.589 | 34 | haiku-4-5-20251001,opus-5 |
| migration-regulated | without_skill | 90% | 280 | 1.681 | 30 | haiku-4-5-20251001,opus-5 |
| pack-no-temporal | with_skill | 100% | 262 | 1.516 | 21 | haiku-4-5-20251001,opus-5 |
| pack-no-temporal | without_skill | 100% | 217 | 1.534 | 29 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 278 | 1.603 | 29 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 67% | 294 | 1.745 | 25 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 80% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-single-container | with_skill | 2 | 4 | 0 | 0 | 9 | 8 | 7 | 6 |
| adversarial-single-container | without_skill | 2 | 3 | 0 | 3 | 8 | 7 | 4 | 3 |
| chat-copilot-no-packs | with_skill | 2 | 3 | 0 | 0 | 7 | 5 | 6 | 5 |
| chat-copilot-no-packs | without_skill | 2 | 4 | 0 | 0 | 9 | 6 | 6 | 4 |
| migration-regulated | with_skill | 2 | 3 | 1 | 2 | 5 | 5 | 6 | 6 |
| migration-regulated | without_skill | 2 | 3 | 2 | 2 | 7 | 6 | 5 | 5 |
| pack-no-temporal | with_skill | 2 | 5 | 2 | 3 | 7 | 5 | 7 | 5 |
| pack-no-temporal | without_skill | 2 | 4 | 2 | 4 | 6 | 5 | 6 | 4 |
| regulated-invoice-intake | with_skill | 2 | 5 | 0 | 2 | 11 | 8 | 7 | 6 |
| regulated-invoice-intake | without_skill | 2 | 4 | 0 | 9 | 12 | 8 | 4 | 3 |

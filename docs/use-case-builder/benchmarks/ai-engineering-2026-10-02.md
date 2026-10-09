# Benchmark — ai-engineering / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-gpt4o-on-financial | with_skill | 100% | 325 | 1.925 | 33 | haiku-4-5-20251001,opus-5 |
| adversarial-gpt4o-on-financial | without_skill | 100% | 213 | 1.433 | 27 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | with_skill | 100% | 315 | 1.659 | 27 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | without_skill | 58% | 182 | 1.186 | 24 | haiku-4-5-20251001,opus-5 |
| migration-no-model-needed | with_skill | 100% | 162 | 1.206 | 28 | haiku-4-5-20251001,opus-5 |
| migration-no-model-needed | without_skill | 100% | 152 | 1.137 | 22 | haiku-4-5-20251001,opus-5 |
| pack-api-only | with_skill | 100% | 285 | 1.775 | 30 | haiku-4-5-20251001,opus-5 |
| pack-api-only | without_skill | 100% | 207 | 1.418 | 25 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 324 | 1.774 | 27 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 57% | 215 | 1.38 | 23 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 83% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-gpt4o-on-financial | with_skill | 2 | 5 | 2 | 6 | 9 | 9 | 10 | 8 |
| adversarial-gpt4o-on-financial | without_skill | 2 | 4 | 1 | 6 | 10 | 8 | 4 | 3 |
| chat-copilot-no-packs | with_skill | 2 | 5 | 0 | 0 | 9 | 8 | 9 | 8 |
| chat-copilot-no-packs | without_skill | 2 | 4 | 0 | 0 | 7 | 8 | 7 | 6 |
| migration-no-model-needed | with_skill | 2 | 1 | 1 | 4 | 5 | 3 | 2 | 2 |
| migration-no-model-needed | without_skill | 2 | 1 | 1 | 4 | 4 | 3 | 2 | 2 |
| pack-api-only | with_skill | 2 | 4 | 3 | 6 | 9 | 10 | 8 | 6 |
| pack-api-only | without_skill | 2 | 4 | 1 | 6 | 5 | 5 | 5 | 3 |
| regulated-invoice-intake | with_skill | 2 | 4 | 1 | 6 | 11 | 10 | 6 | 5 |
| regulated-invoice-intake | without_skill | 2 | 4 | 2 | 6 | 10 | 9 | 4 | 3 |

# Benchmark — ai-engineering / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-gpt4o-on-financial | with_skill | 100% | 215 | 1.295 | 21 | opus-5-5 |
| adversarial-gpt4o-on-financial | without_skill | 100% | 147 | 1.124 | 23 | opus-5-5 |
| chat-copilot-no-packs | with_skill | 100% | 314 | 1.496 | 19 | opus-5-5 |
| chat-copilot-no-packs | without_skill | 50% | 217 | 1.438 | 31 | opus-5-5 |
| migration-no-model-needed | with_skill | 100% | 174 | 1.266 | 29 | opus-5-5 |
| migration-no-model-needed | without_skill | 100% | 88 | 0.683 | 14 | opus-5-5 |
| pack-api-only | with_skill | 100% | 196 | 1.264 | 26 | opus-5-5 |
| pack-api-only | without_skill | 78% | 135 | 1.043 | 23 | opus-5-5 |
| pack-enterprise-posture | with_skill | 100% | 316 | 1.676 | 39 | opus-5-5 |
| pack-enterprise-posture | without_skill | 100% | 284 | 1.426 | 24 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 329 | 1.755 | 27 | opus-5-5 |
| regulated-invoice-intake | without_skill | 52% | 182 | 1.176 | 19 | opus-5-5 |

**with_skill** mean pass rate: 100% over 6 run(s)

**without_skill** mean pass rate: 80% over 6 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-gpt4o-on-financial | with_skill | 1 | 3 | 2 | 6 | 12 | 9 | 10 | 8 |
| adversarial-gpt4o-on-financial | without_skill | 1 | 2 | 1 | 6 | 7 | 5 | 3 | 3 |
| chat-copilot-no-packs | with_skill | 1 | 4 | 0 | 0 | 11 | 11 | 9 | 7 |
| chat-copilot-no-packs | without_skill | 1 | 3 | 0 | 0 | 7 | 8 | 3 | 2 |
| migration-no-model-needed | with_skill | 1 | 1 | 0 | 4 | 8 | 2 | 1 | 1 |
| migration-no-model-needed | without_skill | 1 | 1 | 0 | 4 | 3 | 1 | 1 | 0 |
| pack-api-only | with_skill | 1 | 2 | 2 | 6 | 8 | 7 | 9 | 6 |
| pack-api-only | without_skill | 1 | 2 | 1 | 6 | 5 | 5 | 4 | 4 |
| pack-enterprise-posture | with_skill | 1 | 6 | 1 | 21 | 14 | 10 | 10 | 8 |
| pack-enterprise-posture | without_skill | 1 | 5 | 2 | 22 | 11 | 9 | 6 | 4 |
| regulated-invoice-intake | with_skill | 1 | 4 | 1 | 6 | 13 | 12 | 9 | 7 |
| regulated-invoice-intake | without_skill | 1 | 4 | 2 | 9 | 8 | 8 | 5 | 5 |

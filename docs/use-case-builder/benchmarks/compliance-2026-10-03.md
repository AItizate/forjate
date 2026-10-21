# Benchmark — compliance / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-approve-dpia-and-invent-retention | with_skill | 100% | 330 | 2.17 | 37 | haiku-4-5-20251001,opus-5 |
| adversarial-approve-dpia-and-invent-retention | without_skill | 86% | 202 | 1.365 | 27 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | with_skill | 100% | 247 | 1.563 | 32 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | without_skill | 60% | 230 | 1.612 | 32 | haiku-4-5-20251001,opus-5 |
| migration-regulated | with_skill | 100% | 295 | 1.809 | 27 | haiku-4-5-20251001,opus-5 |
| migration-regulated | without_skill | 85% | 208 | 1.283 | 21 | haiku-4-5-20251001,opus-5 |
| pack-us-only | with_skill | 100% | 252 | 1.882 | 37 | haiku-4-5-20251001,opus-5 |
| pack-us-only | without_skill | 80% | 286 | 1.952 | 32 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 328 | 2.037 | 38 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 53% | 243 | 1.656 | 36 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 73% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-approve-dpia-and-invent-retention | with_skill | 6 | 9 | 1 | 14 | 4 | 10 | 18 | 9 |
| adversarial-approve-dpia-and-invent-retention | without_skill | 6 | 7 | 0 | 14 | 4 | 7 | 15 | 10 |
| chat-copilot-no-packs | with_skill | 5 | 10 | 0 | 0 | 6 | 5 | 15 | 10 |
| chat-copilot-no-packs | without_skill | 5 | 7 | 0 | 0 | 5 | 5 | 13 | 9 |
| migration-regulated | with_skill | 3 | 7 | 3 | 8 | 4 | 5 | 8 | 3 |
| migration-regulated | without_skill | 3 | 3 | 2 | 7 | 4 | 4 | 5 | 1 |
| pack-us-only | with_skill | 6 | 8 | 2 | 18 | 6 | 8 | 15 | 10 |
| pack-us-only | without_skill | 6 | 6 | 3 | 20 | 4 | 8 | 13 | 8 |
| regulated-invoice-intake | with_skill | 6 | 8 | 1 | 18 | 6 | 9 | 17 | 10 |
| regulated-invoice-intake | without_skill | 6 | 7 | 1 | 18 | 1 | 8 | 13 | 8 |

# Benchmark — data-store / iteration-1

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-chat-history-in-minio | with_skill | 100% | 188 | 1.22 | 19 | haiku-4-5-20251001,opus-5 |
| adversarial-chat-history-in-minio | without_skill | 86% | 209 | 1.195 | 20 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | with_skill | 100% | 180 | 1.25 | 24 | haiku-4-5-20251001,opus-5 |
| chat-copilot-no-packs | without_skill | 50% | 155 | 1.262 | 29 | haiku-4-5-20251001,opus-5 |
| migration-regulated | with_skill | 100% | 183 | 1.353 | 26 | haiku-4-5-20251001,opus-5 |
| migration-regulated | without_skill | 92% | 252 | 1.572 | 24 | haiku-4-5-20251001,opus-5 |
| pack-no-postgres | with_skill | 100% | 278 | 1.724 | 25 | haiku-4-5-20251001,opus-5 |
| pack-no-postgres | without_skill | 100% | 205 | 1.43 | 27 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 287 | 1.834 | 30 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 69% | 295 | 2.037 | 37 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 79% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-chat-history-in-minio | with_skill | 2 | 3 | 0 | 0 | 9 | 6 | 6 | 4 |
| adversarial-chat-history-in-minio | without_skill | 2 | 4 | 0 | 0 | 6 | 5 | 4 | 3 |
| chat-copilot-no-packs | with_skill | 2 | 4 | 0 | 0 | 8 | 7 | 7 | 6 |
| chat-copilot-no-packs | without_skill | 2 | 3 | 0 | 0 | 5 | 4 | 6 | 3 |
| migration-regulated | with_skill | 2 | 3 | 1 | 4 | 8 | 6 | 6 | 4 |
| migration-regulated | without_skill | 2 | 3 | 2 | 4 | 7 | 5 | 4 | 2 |
| pack-no-postgres | with_skill | 2 | 4 | 2 | 6 | 11 | 6 | 7 | 5 |
| pack-no-postgres | without_skill | 2 | 4 | 1 | 3 | 11 | 8 | 7 | 5 |
| regulated-invoice-intake | with_skill | 2 | 5 | 0 | 6 | 10 | 9 | 9 | 6 |
| regulated-invoice-intake | without_skill | 2 | 4 | 1 | 6 | 10 | 6 | 6 | 3 |

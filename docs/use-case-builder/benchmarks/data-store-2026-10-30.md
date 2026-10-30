# Benchmark — data-store / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-chat-history-in-minio | with_skill | 100% | 152 | 0.769 | 19 | opus-5-5 |
| adversarial-chat-history-in-minio | without_skill | 57% | 107 | 0.757 | 14 | opus-5-5 |
| chat-copilot-no-packs | with_skill | 100% | 145 | 0.977 | 23 | opus-5-5 |
| chat-copilot-no-packs | without_skill | 71% | 154 | 1.071 | 23 | opus-5-5 |
| migration-regulated | with_skill | 100% | 179 | 1.046 | 33 | opus-5-5 |
| migration-regulated | without_skill | 100% | 110 | 0.804 | 15 | opus-5-5 |
| pack-no-postgres | with_skill | 100% | 180 | 0.988 | 20 | opus-5-5 |
| pack-no-postgres | without_skill | 89% | 109 | 0.915 | 17 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 224 | 1.129 | 22 | opus-5-5 |
| regulated-invoice-intake | without_skill | 100% | 173 | 1.212 | 18 | opus-5-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 83% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-chat-history-in-minio | with_skill | 1 | 3 | 0 | 0 | 8 | 5 | 6 | 3 |
| adversarial-chat-history-in-minio | without_skill | 1 | 1 | 0 | 0 | 3 | 7 | 2 | 0 |
| chat-copilot-no-packs | with_skill | 1 | 1 | 0 | 0 | 9 | 6 | 6 | 2 |
| chat-copilot-no-packs | without_skill | 1 | 2 | 0 | 0 | 5 | 3 | 2 | 0 |
| migration-regulated | with_skill | 1 | 3 | 1 | 4 | 10 | 7 | 7 | 5 |
| migration-regulated | without_skill | 1 | 2 | 2 | 4 | 4 | 4 | 2 | 1 |
| pack-no-postgres | with_skill | 1 | 4 | 2 | 6 | 11 | 7 | 8 | 3 |
| pack-no-postgres | without_skill | 1 | 3 | 2 | 6 | 8 | 5 | 2 | 1 |
| regulated-invoice-intake | with_skill | 1 | 6 | 0 | 6 | 14 | 8 | 6 | 2 |
| regulated-invoice-intake | without_skill | 1 | 3 | 1 | 8 | 8 | 8 | 4 | 2 |

# Benchmark — coordinator / iteration-4

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| cold-start-with-answers | with_skill | 100% | 303 | 1.503 | 15 | opus-5-5 |
| cold-start-with-answers | without_skill | 86% | 130 | 0.902 | 17 | opus-5-5 |
| resume-does-not-reinterview | with_skill | 100% | 285 | 1.454 | 25 | opus-5-5 |
| resume-does-not-reinterview | without_skill | 88% | 93 | 0.654 | 24 | opus-5-5 |
| review-tenant-drift | with_skill | 100% | 58 | 0.55 | 23 | opus-5-5 |
| review-tenant-drift | without_skill | 100% | 93 | 0.564 | 26 | opus-5-5 |
| vague-prompt-records-assumptions | with_skill | 100% | 193 | 1.203 | 19 | opus-5-5 |
| vague-prompt-records-assumptions | without_skill | 83% | 130 | 0.896 | 21 | opus-5-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

**without_skill** mean pass rate: 89% over 4 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| cold-start-with-answers | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cold-start-with-answers | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| resume-does-not-reinterview | with_skill | 2 | 8 | 2 | 4 | 6 | 13 | 6 | 2 |
| resume-does-not-reinterview | without_skill | 2 | 3 | 1 | 2 | 1 | 2 | 3 | 0 |
| review-tenant-drift | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| review-tenant-drift | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vague-prompt-records-assumptions | with_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vague-prompt-records-assumptions | without_skill | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

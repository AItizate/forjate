# Benchmark — app-scaffold / iteration-4

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-hand-rolled-pipeline | with_skill | 100% | 1658 | 17.334 | 161 | haiku-4-5-20251001,opus-5 |
| adversarial-hand-rolled-pipeline | without_skill | 65% | 1814 | 15.702 | 126 | haiku-4-5-20251001,opus-5 |
| invoice-intake-batch | with_skill | 100% | 1707 | 15.509 | 119 | haiku-4-5-20251001,opus-5 |
| invoice-intake-batch | without_skill | 96% | 1631 | 12.272 | 121 | haiku-4-5-20251001,opus-5 |
| pack-tool-logging | with_skill | 100% | 1640 | 12.933 | 123 | haiku-4-5-20251001,opus-5 |
| pack-tool-logging | without_skill | 100% | 1469 | 11.453 | 130 | haiku-4-5-20251001,opus-5 |
| support-copilot-api | with_skill | 100% | 1884 | 16.787 | 137 | haiku-4-5-20251001,opus-5 |
| support-copilot-api | without_skill | 92% | 1693 | 13.566 | 117 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 4 run(s)

**without_skill** mean pass rate: 88% over 4 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-hand-rolled-pipeline | with_skill | 1 | 3 | 1 | 6 | 7 | 10 | 12 | 11 |
| adversarial-hand-rolled-pipeline | without_skill | 1 | 3 | 1 | 6 | 7 | 10 | 12 | 11 |
| invoice-intake-batch | with_skill | 1 | 3 | 1 | 6 | 7 | 10 | 12 | 11 |
| invoice-intake-batch | without_skill | 1 | 3 | 1 | 6 | 7 | 10 | 12 | 11 |
| pack-tool-logging | with_skill | 2 | 6 | 0 | 0 | 8 | 9 | 12 | 10 |
| pack-tool-logging | without_skill | 2 | 6 | 0 | 0 | 8 | 9 | 12 | 10 |
| support-copilot-api | with_skill | 2 | 6 | 0 | 0 | 8 | 9 | 12 | 10 |
| support-copilot-api | without_skill | 2 | 6 | 0 | 0 | 8 | 9 | 12 | 10 |

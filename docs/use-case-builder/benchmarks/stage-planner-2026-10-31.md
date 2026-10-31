# Benchmark — stage-planner / iteration-4

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| chat-copilot-stops-at-walk | with_skill | 100% | 111 | 0.657 | 9 | opus-5-5 |
| chat-copilot-stops-at-walk | without_skill | 100% | 91 | 0.631 | 14 | opus-5-5 |
| deterministic-migration-skips-ai | with_skill | 100% | 133 | 0.797 | 18 | opus-5-5 |
| deterministic-migration-skips-ai | without_skill | 100% | 112 | 0.856 | 22 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 156 | 0.873 | 20 | opus-5-5 |
| regulated-invoice-intake | without_skill | 94% | 121 | 0.75 | 17 | opus-5-5 |

**with_skill** mean pass rate: 100% over 3 run(s)

**without_skill** mean pass rate: 98% over 3 run(s)

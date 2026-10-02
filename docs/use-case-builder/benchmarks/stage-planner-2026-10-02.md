# Benchmark — stage-planner / iteration-3

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| chat-copilot-stops-at-walk | with_skill | 100% | 128 | 0.948 | 20 | haiku-4-5-20251001,opus-5 |
| chat-copilot-stops-at-walk | without_skill | 100% | 668 | 0.799 | 15 | haiku-4-5-20251001,opus-5 |
| deterministic-migration-skips-ai | with_skill | 100% | 128 | 0.803 | 18 | haiku-4-5-20251001,opus-5 |
| deterministic-migration-skips-ai | without_skill | 100% | 122 | 0.872 | 17 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | with_skill | 100% | 198 | 1.164 | 23 | haiku-4-5-20251001,opus-5 |
| regulated-invoice-intake | without_skill | 92% | 248 | 1.414 | 20 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 3 run(s)

**without_skill** mean pass rate: 97% over 3 run(s)

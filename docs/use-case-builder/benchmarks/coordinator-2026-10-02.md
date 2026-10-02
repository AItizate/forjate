# Benchmark — coordinator / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| cold-start-with-answers | with_skill | 100% | 326 | 1.946 | 28 | haiku-4-5-20251001,opus-5 |
| cold-start-with-answers | without_skill | 8% | 747 | 4.246 | 62 | haiku-4-5-20251001,opus-5 |
| resume-does-not-reinterview | with_skill | 100% | 79 | 0.608 | 18 | haiku-4-5-20251001,opus-5 |
| resume-does-not-reinterview | without_skill | 57% | 656 | 4.974 | 61 | haiku-4-5-20251001,opus-5 |
| vague-prompt-records-assumptions | with_skill | 100% | 1198 | 1.783 | 26 | haiku-4-5-20251001,opus-5 |
| vague-prompt-records-assumptions | without_skill | 60% | 599 | 2.817 | 44 | haiku-4-5-20251001,opus-5 |

**with_skill** mean pass rate: 100% over 3 run(s)

**without_skill** mean pass rate: 42% over 3 run(s)

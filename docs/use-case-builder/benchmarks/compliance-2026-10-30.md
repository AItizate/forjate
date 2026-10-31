# Benchmark — compliance / iteration-2

| eval | config | pass rate | seconds | cost USD | turns | models |
|---|---|---|---|---|---|---|
| adversarial-approve-dpia-and-invent-retention | with_skill | 100% | 198 | 1.163 | 31 | opus-5-5 |
| adversarial-approve-dpia-and-invent-retention | without_skill | 100% | 116 | 0.849 | 21 | opus-5-5 |
| chat-copilot-no-packs | with_skill | 100% | 223 | 1.332 | 27 | opus-5-5 |
| chat-copilot-no-packs | without_skill | 56% | 173 | 1.05 | 20 | opus-5-5 |
| migration-regulated | with_skill | 100% | 240 | 1.365 | 34 | opus-5-5 |
| migration-regulated | without_skill | 100% | 128 | 0.936 | 19 | opus-5-5 |
| pack-us-only | with_skill | 100% | 307 | 1.682 | 45 | opus-5-5 |
| pack-us-only | without_skill | 80% | 254 | 1.443 | 33 | opus-5-5 |
| regulated-invoice-intake | with_skill | 100% | 235 | 1.463 | 35 | opus-5-5 |
| regulated-invoice-intake | without_skill | 57% | 236 | 1.345 | 36 | opus-5-5 |

**with_skill** mean pass rate: 100% over 5 run(s)

**without_skill** mean pass rate: 79% over 5 run(s)

## Quality metrics (decision records produced by the run)

| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |
|---|---|---|---|---|---|---|---|---|---|
| adversarial-approve-dpia-and-invent-retention | with_skill | 1 | 7 | 1 | 9 | 0 | 7 | 11 | 3 |
| adversarial-approve-dpia-and-invent-retention | without_skill | 1 | 4 | 1 | 9 | 4 | 7 | 6 | 1 |
| chat-copilot-no-packs | with_skill | 1 | 10 | 0 | 0 | 7 | 8 | 11 | 3 |
| chat-copilot-no-packs | without_skill | 1 | 5 | 0 | 0 | 5 | 6 | 6 | 3 |
| migration-regulated | with_skill | 1 | 6 | 2 | 6 | 6 | 9 | 10 | 3 |
| migration-regulated | without_skill | 1 | 2 | 0 | 5 | 0 | 5 | 5 | 2 |
| pack-us-only | with_skill | 1 | 12 | 3 | 15 | 5 | 9 | 13 | 4 |
| pack-us-only | without_skill | 1 | 5 | 3 | 15 | 0 | 5 | 6 | 3 |
| regulated-invoice-intake | with_skill | 1 | 10 | 2 | 9 | 4 | 10 | 15 | 5 |
| regulated-invoice-intake | without_skill | 1 | 5 | 1 | 9 | 3 | 7 | 6 | 3 |

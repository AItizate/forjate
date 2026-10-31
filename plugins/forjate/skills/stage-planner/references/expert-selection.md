# Expert selection

Every role gets an entry in `spec.experts`. `run: true` or a one-sentence `skip_reason`.

| Role | Run when | Safe to skip when |
|------|----------|-------------------|
| `business` | always | never |
| `architecture` | always for anything with more than one component | a single Job with no integration |
| `ai-engineering` | a model makes decisions, generates, classifies, or converses | deterministic ETL, CDC, migrations, pure infra |
| `data-store` | the use case keeps state beyond one run | stateless pass-through with no memory |
| `data-pipeline` | data moves in, out or between systems | the input is a single manual upload and nothing leaves |
| `security` | always from Walk; at Crawl when data is `pii`, `financial`, `health` or `secret`, when a tool writes to a system of record, when a surface is exposed, or when the brief carries a `risk_profile` (security in week one) | Crawl-only on `none`/`internal` data with no write, no surface and no risk profile |
| `compliance` | `regulated: true`, residency set, or data class is `pii`/`financial`/`health` | internal tooling on `none`/`internal` data with no residency constraint |
| `quality` | always | never |
| `devops` | always from Walk; at Crawl only to size the ephemeral env | Crawl-only use cases where `ephemeral.sh` is the whole story |
| `ux` | a human uses the result interactively (chat, UI, review queue), or `risk_profile` includes `customer-facing` or `vulnerable-population` (disclosure and a review that validates are its decisions) | batch, operator-only, API consumed by another system |

Running an expert costs a subagent turn and adds a record a reviewer has to read. Skipping one wrongly costs a missing decision that surfaces late. When in doubt, run it and let the expert return a short record.

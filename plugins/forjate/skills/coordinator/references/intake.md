# Intake

Six questions is the ceiling. The problem statement usually answers two or three already; ask only the rest. Prefer one `AskUserQuestion` call with several questions over a back-and-forth.

## The question bank, in priority order

1. **Language and packs** (always, unless known). "Which language should the documents be written in?" with `en` as the recommended default. "Which organisation rules apply?" listing the packs found under `context-packs/` and `~/.forjate/packs/`, plus "none".
2. **Success**. "What single number will tell you this worked?" → `success.metric`, with `baseline` and `target` if they know them. This is the question people skip and the one the quality expert needs most.
3. **Data**. "What data does this touch, and does any of it identify people, money or health?" → `data.sources` and `data.classification`. Ask residency only if the answer is not `none`/`internal`.
4. **Actors and approver**. "Who uses the result, who runs it, and who signs off before it goes live?" → `actors`. The approver is a gate owner; without one the plan has no manual gates.
5. **Constraints**. "Regulated? Budget per month? Must it integrate with specific systems? May data go to an external model provider? Several clients or tenants on it, and must they be kept apart? Must everything stay on open standards the organisation can rebuild? Which languages does your team build and operate?" → `constraints`, `isolation` (`physical` / `logical` / `none`), `constraints.open_standards_required`, `constraints.stack` (a list of `python`, `typescript`, `go`; absent when they have no preference, and the architecture expert decides). Ask `llm_egress_allowed` explicitly when classification is `pii`, `financial` or `health`; ask `isolation` only when more than one client or tenant is in the picture.
6. **Ambition and autonomy**. "Is this a proof of concept, something colleagues will rely on, or something customers will depend on? At the end, should the agent recommend while a person acts, act with a person approving its writes, or act on its own? What makes a wrong action costly here: a regulated decision, a vulnerable person on the other side, a high-impact or irreversible action, a customer facing it?" → `stages_requested` (crawl / crawl+walk / all three), `autonomy` (`assistive` / `semi-autonomous` / `autonomous`), `risk_profile` (a list). Whatever the answer, Crawl is assistive: say so when the requester asks for autonomy, the planner sets the ceiling per stage.

## Deriving fields without asking

- `name`: a noun phrase from the problem, e.g. "read supplier invoices and post them to the ERP" → `invoice-intake`. Check the directory does not already exist.
- `data.classification`: invoices, payroll, bank data → `financial`; customers, employees, chats with people → `pii`; patient anything → `health`; otherwise `internal`. When in doubt, the higher class; the compliance expert can relax it with a reason.
- `constraints.regulated`: `true` when the brief mentions audit, compliance, a regulator, or the data class is `financial`/`health`.
- `risk_profile`: `regulated-decision` when the agent's output feeds a decision a regulator audits; `high-impact-action` or `irreversible-action` when a tool posts, pays, deletes or sends; `customer-facing` when the actors include customers or the public; `vulnerable-population` when patients, minors or people in distress are on the other side. Empty for internal tooling with no write.
- `autonomy`: `semi-autonomous` when the problem says "a person approves" or names a human in the loop, `assistive` when it says "suggest", "draft" or "recommend", `autonomous` only when the requester says so; the planner caps every stage regardless.
- `isolation`: `none` unless several clients, tenants or business units are named, then `logical`; `physical` only when the requester says a client must have its own environment.
- `constraints.open_standards_required`: `true` when the brief mentions portability, vendor lock-in, open source policy or a public-sector buyer.
- `requested_by`: the user, unless they name someone.

## When nobody can answer

Non-interactive runs and users who say "just assume" get conservative defaults, each written as an `ASSUMED:` line in `constraints.notes`:

- language `en`, no packs
- classification by the rule above
- `llm_egress_allowed: false` for `pii`/`financial`/`health`, `true` otherwise
- `stages_requested: [crawl, walk]`
- `autonomy: assistive`, `risk_profile` by the rule above, `isolation: none`, `open_standards_required` unset
- success metric phrased from the problem ("share of <things> handled without a person"), baseline and target left unset

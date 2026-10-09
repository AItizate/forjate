# Intake

Six questions is the ceiling. The problem statement usually answers two or three already; ask only the rest. Prefer one `AskUserQuestion` call with several questions over a back-and-forth.

## The question bank, in priority order

1. **Language and packs** (always, unless known). "Which language should the documents be written in?" with `en` as the recommended default. "Which organisation rules apply?" listing the packs found under `context-packs/` and `~/.forjate/packs/`, plus "none".
2. **Success**. "What single number will tell you this worked?" → `success.metric`, with `baseline` and `target` if they know them. This is the question people skip and the one the quality expert needs most.
3. **Data**. "What data does this touch, and does any of it identify people, money or health?" → `data.sources` and `data.classification`. Ask residency only if the answer is not `none`/`internal`.
4. **Actors and approver**. "Who uses the result, who runs it, and who signs off before it goes live?" → `actors`. The approver is a gate owner; without one the plan has no manual gates.
5. **Constraints**. "Regulated? Budget per month? Must it integrate with specific systems? May data go to an external model provider?" → `constraints`. Ask `llm_egress_allowed` explicitly when classification is `pii`, `financial` or `health`.
6. **Ambition**. "Is this a proof of concept, something colleagues will rely on, or something customers will depend on?" → `stages_requested` (crawl / crawl+walk / all three).

## Deriving fields without asking

- `name`: a noun phrase from the problem, e.g. "read supplier invoices and post them to the ERP" → `invoice-intake`. Check the directory does not already exist.
- `data.classification`: invoices, payroll, bank data → `financial`; customers, employees, chats with people → `pii`; patient anything → `health`; otherwise `internal`. When in doubt, the higher class; the compliance expert can relax it with a reason.
- `constraints.regulated`: `true` when the brief mentions audit, compliance, a regulator, or the data class is `financial`/`health`.
- `requested_by`: the user, unless they name someone.

## When nobody can answer

Non-interactive runs and users who say "just assume" get conservative defaults, each written as an `ASSUMED:` line in `constraints.notes`:

- language `en`, no packs
- classification by the rule above
- `llm_egress_allowed: false` for `pii`/`financial`/`health`, `true` otherwise
- `stages_requested: [crawl, walk]`
- success metric phrased from the problem ("share of <things> handled without a person"), baseline and target left unset

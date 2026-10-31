# How to add an expert

An expert is a skill (knowledge), an agent (isolation) and an eval suite (proof), plus the places that must know it exists. Copy the closest existing expert; `security` is the reference for a governance expert, `ux` for one that shares a setting with others.

## 1. The skill: `plugins/forjate/skills/<role>/`

- `SKILL.md` under 500 lines (CI fails above), with a pushy `description` that names the decisions the expert makes and the phrases that should trigger it, `user-invocable: true`, `argument-hint: "<usecase-dir>"`, and an `allowed-tools` line with only what it needs.
- Sections, in this order: who it is and what it never decides alone; inputs and output; the procedure (numbered, ending with `validate.py` and the short reply); the record (a table of the `settings` keys with their enum values, and a `choice` paragraph naming the capabilities it resolves); the **Governance posture** (a table `key | values | default Crawl → Walk → Run | owner` for every governance setting the expert owns or copies per `contracts.md` "Governance settings", then one bullet per rule with its reason; a test keeps the table and `contracts.md` equal); judgement calls (one bold sentence each, with the reason); when you push back; the **Context packs** section pasted verbatim from `skills/context-pack/references/section.md` with `<role>` filled in and one paragraph on which rule types matter to this role; see also.
- `references/` split by stage or by domain (`secrets-ladder.md`, `network-and-psa.md`), each opened on demand by the procedure. Prose that applies to every decision goes in SKILL.md; tables and snippets go in references.
- Ask by catalog capability and property, not component name, wherever the catalog has more than one option (`contracts.md`, "Catalog capabilities"); if the expert resolves components, add it to `asked_by` in `wiki/catalog-capabilities.yaml` so it gets a `references/catalog-snapshot.md`. `skill-lint.py --strict` runs in CI and fails on any catalog path outside the snapshot; a rule of judgement that uses a component as an illustration ends its line with `<!-- skill-lint: allow -->`.
- If the expert measures something only it can, it contributes `eval_dimensions` lines (`quality/references/eval-dimensions.md`); the quality expert consolidates them.

## 2. The agent: `plugins/forjate/agents/<role>.md`

Frontmatter: `name`, a `description` that says when to delegate, `tools: Read, Grep, Glob, Write, Bash`, `model: inherit`, `skills: [<role>, context-pack]`. Body: three paragraphs — the deliverable (one file, validated), how to work (from the records and the packs, no interviews, open questions instead of silent changes), what to return (the path and five lines; nothing else).

## 3. The record's keys

List the `settings` keys the expert emits in `experts.md` (inputs, emits, pushes back when, never decides alone). If a pack rule should match one of them, add it to the table in `contracts.md`. If the expert can conflict with another on a component group or a shared setting, register it in `validate.py`: the group in `EXCLUSIVE_GROUPS`, the setting in `SHARED_SETTINGS`, a setting that implies a component in `SETTING_TO_GROUP`, each with a test in `scripts/builder/tests/`.

## 4. The evals: `plugins/forjate/evals/<role>/evals.json`

Five evals: the three golden briefs (`fixtures/briefs/`, `fixtures/plans/`, the core records under `fixtures/decisions/<uc>/` and, when the expert reads a governance record, the one it needs from `fixtures/records/<uc>/`), one adversarial prompt (the requester asks for the thing the expert must refuse), one pack eval with a fixture pack under `fixtures/packs/` that forbids the expert's default, layered over `regulated-corp`. Every eval mixes form checks (`file_exists`, `schema_valid`, `usecase_valid`) with judgement checks (`yaml_expr` over the record: a rule cited, an open question with `caused_by_rule`, an alternative rejected with a reason, a default refused). Where two records can legitimately differ, assert "agrees or asks". Sanity-check the assertions against a hand-written record before running anything.

## 5. Wire it

- `plugins/forjate/skills/coordinator/SKILL.md`: add the role to the list of available experts and to the wave-2 fan-out.
- `plugins/forjate/skills/stage-planner/references/expert-selection.md`: when it runs, when it is safe to skip.
- `_defs.schema.json` already lists every role; add a new one there and in `common.py` `ROLES` only if the role is new.
- `plugins/forjate/README.md`: the roles line.

## 6. Run the evals

```bash
caffeinate -i -s ./plugins/forjate/evals/run.sh <role> --model opus     # with and without the plugin, in series
python3 plugins/forjate/evals/grade.py --all evals-workspace/<role>/iteration-1
```

Read the record before touching the skill when a with-skill assertion fails: half the time the assertion is wrong (`plan.md` §3). Copy the final `benchmark.md` to `docs/use-case-builder/benchmarks/<role>-<date>.md` and add the row to `plan.md`.

## Builders are not experts

`app-scaffold` and `kustomize` decide nothing: they turn records into code and manifests. A builder has the same skill and agent shape, no decision record, and a machine-checkable artifact instead (`scaffold.yaml`, the overlay) with a checker in `scripts/builder/` (`scaffold-check.py`) or a gate check in `scripts/gates/checks/`. Its evals assert that the output builds, its tests pass and it matches the records, not that it chose well.

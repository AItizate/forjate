# Skill evals

How the mechanism works end to end: `docs/use-case-builder/evals.md`. This page is the operating reference.

Level-1 tests from `docs/use-case-builder/plan.md` §3: every skill has a few realistic prompts, each run twice — with the plugin loaded and without it (baseline) — in an isolated git worktree, then graded by objective assertions. The point of the baseline is to prove the skill changes behaviour; a skill whose pass-rate equals the baseline is dead weight. Because the plugin lives in this repo, the baseline worktree has `plugins/forjate/skills`, `agents` and `docs/use-case-builder` removed; otherwise the model reads the skills off disk and the control is meaningless. The golden use cases `invoice-intake` and `support-copilot` are committed with their records, apps and overlays, which are the answers the evals ask for: `run.sh` strips both directories from every worktree (both configurations) and a skill that needs a subpath as input lists it in `evals/<skill>/worktree-keep` (kustomize keeps `app/` for the assembly eval).

```
evals/
├── run.sh            # run.sh <skill> [--iteration N] [--eval <id>] [--only with|without] [--model m] [--timeout s]
├── grade.py          # grade.py <run-dir>  → grading.json  (also: --all <iteration-dir> → benchmark.md)
└── <skill>/evals.json
```

Fixtures: `fixtures/briefs/`, `fixtures/plans/`, `fixtures/decisions/<uc>/` (the core five records an expert eval copies in), `fixtures/records/<uc>/` (the complete set of ten plus `fixtures/gates/<uc>.yaml`, what the assembly, scaffold and gates evals consume; its core five are byte-identical copies of `decisions/`, a test asserts it), `fixtures/packs/`.

Results land in `evals-workspace/<skill>/iteration-N/<eval-name>/{with_skill,without_skill}/` (git-ignored): `result.json` (claude -p output incl. duration and cost), `repo/` (the worktree after the run), `grading.json`.

## Assertion types

| type | args | passes when |
|------|------|-------------|
| `file_exists` | `path` | the file exists in the worktree |
| `file_absent` | `path` | it does not |
| `grep` | `path`, `pattern` | regex matches the file |
| `not_grep` | `path`, `pattern` | regex does not match |
| `kustomize_builds` | `path` | `kubectl kustomize` exits 0 |
| `kubeconform` | `path` | the built manifest passes kubeconform |
| `usecase_valid` | `path` | `validate.py` exits 0 on that use case |
| `pack_lint` | `path` | `packs.py lint` exits 0 |
| `yaml_path` | `path`, `query`, `equals` | `yq` query result equals the value |
| `components_in_catalog` | `path` | every component listed in that `usecase.yaml` exists |
| `git_unchanged` | `path` | the file is identical to HEAD (the skill must not touch it) |
| `schema_valid` | `path`, `schema` | the YAML validates against `scripts/builder/schemas/<schema>.schema.json` |
| `command` | `cmd` | a shell command exits 0 in the worktree (a generated service builds, its tests pass) |
| `scaffold_check` | `path` | `scaffold-check.py` exits 0 on that use case (tool signatures match the AI-engineering record, templates @v1, no hand-rolled build) |
| `yaml_expr` | `path`, `expr` | a Python expression over the loaded YAML is truthy; helpers: `d`, `stages`, `setting(key[, stage])`, `choices([stage])`, `choice_capabilities([stage])`, `capabilities_of(component)`, `psa_exceptions([stage])`, `psa_level_of(component)`, `namespace_of(component)` (the last two read `wiki/catalog.json`), `alts()`, `risks()`, `gates()`, `rules()`, `oq()`, `has(regex, x)`, `txt(x)`, `listed(x)` |
| `choice_has_capability` | `path`, `capability`, optional `stage` | some component in the record's `choice` (of that stage, or any) has that catalog capability per `wiki/catalog.json`; asserts the role a choice plays, not its name |
| `choice_lacks_capability` | `path`, `capability`, optional `stage` | no chosen component has it ("no vector store") |

Assert capabilities, not component names: `choice_has_capability` with `session-memory` keeps passing when a better store joins the catalog, `has('redis', ...)` does not. A name is acceptable only for a capability with a single option (the skill's `references/catalog-snapshot.md` says which). Assertions check outputs, not transcripts. Tone and clarity are reviewed by a human reading `result.json`. Every expert eval mixes form checks (schema, validator) with judgement checks (a pack rule cited, an open question raised with `caused_by_rule`, an alternative rejected with a reason, a default refused); the form checks stop discriminating against a frontier baseline fast.

`grade.py --all` also computes **quality metrics** per run from the decision records it finds (open questions, questions caused by a pack rule, pack refs, alternatives, risks, gates and automated gates) and appends them to `benchmark.md`; they are where a skill's value shows when pass rates tie.

## Run

```bash
./plugins/forjate/evals/run.sh kustomize                      # all evals, both configurations
./plugins/forjate/evals/run.sh kustomize --eval add-redis     # one eval
python3 plugins/forjate/evals/grade.py --all evals-workspace/kustomize/iteration-1
```

Needs `claude` on PATH, `kubectl`, `kubeconform`, `yq`, and the repo's poetry env.

Runs use **Opus** by default (`--model` or `FORJATE_EVAL_MODEL` to change) and 40 turns (`--max-turns` or `FORJATE_EVAL_MAX_TURNS`); the builders need `--max-turns 120`, a scaffold writes dozens of files and 40 turns end in `error_max_turns`, recorded as `is_error`. Every run has a timeout (`--timeout`, `FORJATE_EVAL_TIMEOUT`, default 1800 s): a hung `claude -p` is killed, not waited on. A run that hits the timeout or the account's session limit is recorded with `is_error: true` in `timing.json` and must be re-run; the benchmark is not meaningful until every row has a real duration. Run batches in series and never re-run an eval while another run of it is alive: each run owns one worktree.

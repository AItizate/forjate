# Skill evals

Level-1 tests from `docs/use-case-builder/plan.md` §3: every skill has a few realistic prompts, each run twice — with the plugin loaded and without it (baseline) — in an isolated git worktree, then graded by objective assertions. The point of the baseline is to prove the skill changes behaviour; a skill whose pass-rate equals the baseline is dead weight. Because the plugin lives in this repo, the baseline worktree has `plugins/forjate/skills`, `agents` and `docs/use-case-builder` removed; otherwise the model reads the skills off disk and the control is meaningless.

```
evals/
├── run.sh            # run.sh <skill> [--iteration N] [--eval <id>] [--only with|without]
├── grade.py          # grade.py <run-dir>  → grading.json  (also: --all <iteration-dir> → benchmark.md)
└── <skill>/evals.json
```

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

Assertions check outputs, not transcripts. Tone and clarity are reviewed by a human reading `result.json`.

## Run

```bash
./plugins/forjate/evals/run.sh kustomize                      # all evals, both configurations
./plugins/forjate/evals/run.sh kustomize --eval add-redis     # one eval
python3 plugins/forjate/evals/grade.py --all evals-workspace/kustomize/iteration-1
```

Needs `claude` on PATH, `kubectl`, `kubeconform`, `yq`, and the repo's poetry env.

Runs use **Opus** by default (`--model` or `FORJATE_EVAL_MODEL` to change). A run that hits the account's session limit is recorded with `is_error: true` in `timing.json` and must be re-run; the benchmark is not meaningful until every row has a real duration.

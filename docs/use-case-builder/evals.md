# How the skill evals work

The builder's skills are tested the way the skill-creator pattern recommends: realistic prompts, run with and without the skill, graded by objective assertions, reviewed by a human. This page explains the mechanism end to end. Operating commands and the assertion vocabulary are in `plugins/forjate/evals/README.md`; the strategy and the lessons that shaped it are in `plan.md` §3.

## The question an eval answers

Not "does the skill produce a valid file" but "does the skill change what the model does". A frontier model given the schema path writes a valid record on its own, so validity is table stakes. What the evals measure is judgement: a pack rule cited, an open question raised instead of a silent guess, an alternative rejected with a reason, a gate expressed as something a machine can check. Every eval carries both kinds of assertion, and the benchmark reports pass rate per configuration so the difference is visible.

## The pieces

```
plugins/forjate/evals/
├── run.sh            runs one skill's evals, both configurations, isolated
├── evals_meta.py     helper: writes eval_metadata.json + prompt.txt per eval
├── grade.py          checks assertions, writes grading.json and benchmark.md
├── fixtures/         golden briefs, plans, decision records and packs shared by evals
└── <skill>/evals.json    the prompts and assertions of one skill
```

`evals.json` has one entry per eval: `name`, `prompt` (what a user would type, with every input the run needs named by path), `expected_output` (prose, for the human reviewer) and `assertions` (typed, see the README). Twelve skills have suites today: three evals for the phase 0 and 1 skills, five for each expert (the three golden briefs, one adversarial prompt, one pack eval that forbids the expert's default choice).

## One run

For every eval, `run.sh` performs the same sequence twice, once per configuration:

1. **Isolate.** `git worktree add --detach` at `HEAD` under `evals-workspace/<skill>/iteration-N/<eval>/<with|without>_skill/repo`. The run can write anything; the main checkout is untouched. The main checkout's `.venv` is symlinked in so `poetry run` and the builder scripts work.
2. **Seed.** Gitignored `.env` files are copied from their `.env.example`, as CI does, so overlays build.
3. **Strip the control.** For `without_skill`, `plugins/forjate/skills`, `plugins/forjate/agents` and `docs/use-case-builder` are deleted from the worktree. The plugin is checked into this repo, so without this step the "baseline" reads the skills off disk and the comparison is meaningless. The builder scripts and schemas stay, because the prompts cite them and the baseline must be able to validate too.
4. **Run.** `claude -p "<prompt>" --output-format json --permission-mode acceptEdits --max-turns N --model opus --allowedTools "<list>"`, plus `--plugin-dir plugins/forjate` for `with_skill`. The allowlist pre-approves the build and validate commands the skills use (`kubectl kustomize`, `kubeconform`, `poetry run`, `yq`, the scaffolder) and the `Agent` and `Skill` tools, so a skill that delegates or validates is not blocked by a permission prompt nobody can answer. Stdin is `/dev/null`.
5. **Watch the clock.** The runner polls every 15 seconds and kills the process at the deadline (default 1800 s). A hung `claude -p` consumes nothing and never returns on its own, and a sleep-based watchdog does not fire while the laptop is suspended, so the deadline is wall-clock.
6. **Record.** `result.json` (the CLI's JSON: final answer, turns, cost, `modelUsage`, `subagent_stats`, `permission_denials`) and `timing.json` (duration, turns, cost, models, `is_error`). A session-limit hit or a timeout sets `is_error: true`; that run is re-run, never counted as a failure.

## Grading

`grade.py` reads each run's `eval_metadata.json`, evaluates every assertion against the worktree, and writes `grading.json` with `{text, passed, evidence}` per assertion, the field names the skill-creator viewer expects. Assertions check outputs on disk, never transcripts: a file exists, a `yq` query equals a value, an overlay builds, `validate.py` passes, a pack rule is cited, a file the skill must not touch is unchanged against `HEAD`. Checks that need the builder's Python run with the main checkout's venv.

`grade.py --all <iteration-dir>` grades every run and writes `benchmark.md`: one row per eval and configuration with pass rate, seconds, cost, turns and models, and the mean per configuration. The final benchmark of each skill is copied to `benchmarks/<skill>-<date>.md` as the phase's evidence.

Pass rate alone ties too often, so the analysis also computes quality metrics over the produced artifacts with `yq`: gates by check type, pack references, `OPEN:` lines, experts skipped. These are where the skill's value showed when both configurations scored 100 %.

## Orchestration

Batches are long (five evals × two configurations × a few minutes each) and cost real money, so they run in the background and are delegated to one subagent per batch, on Opus, whose only job is to run `run.sh`, grade, re-run anything flagged `is_error`, and report the benchmark, the failed assertions with evidence and the quality metrics. No transcripts come back to the session that authored the skill; it reads the record only when a with-skill assertion fails, because half the time the assertion is what is wrong.

Rules that came from breaking them: batches run in series, never two at once; a configuration is never re-run while another run of the same eval is alive (two runs on one worktree path destroy each other); the machine stays awake (`caffeinate -i -s`) for the length of a batch.

## The iteration loop

1. Write or change the skill.
2. Run the batch; grade.
3. Read the failures. If the record reasons better than the assertion, fix the assertion. If the skill missed a rule, fix the skill, in a general form, not a patch for the one prompt.
4. Re-run only what changed (`--only with`, `--eval <name>`), as a new iteration or in place.
5. Copy the final `benchmark.md` to `benchmarks/`; record the result and any lesson in `plan.md`.

Stop when the with-skill configuration passes everything, the baseline fails the judgement assertions, and the quality metrics favour the skill on the pack evals. A tie at 100 % on a pack eval means the assertion is too easy, not that the skill is useless; it is logged for Phase 5.

## Adding evals for a new skill

1. Create `plugins/forjate/evals/<role>/evals.json` with the three golden briefs (`fixtures/briefs/`), one adversarial prompt that asks for something the skill must push back on, and one pack eval that forbids the skill's default choice through a pack layered over `context-packs/examples/regulated-corp` (team scope, precedence 30, under `fixtures/packs/`).
2. Give every eval form assertions (file exists, `schema_valid`, `usecase_valid`) and at least two judgement assertions. For checks across two records, assert "agrees or asks": an expert that raises a question instead of mirroring another record is doing its job.
3. Name every input by path in the prompt. The baseline must be able to do the task; it just has no skill to tell it how.
4. Run, grade, iterate, copy the benchmark.

## Levels beyond L1

`plan.md` §3 defines four levels. L1 is this page. L2 is `validate.py` on every `.builder/` artifact, run by CI on every PR. L3 runs the coordinator from cold on a golden use case and proves the Crawl overlay on a k3d cluster with `ephemeral.sh up` (Phase 4). L4 is trigger-accuracy evaluation of every skill's description with the skill-creator loop (Phase 5).

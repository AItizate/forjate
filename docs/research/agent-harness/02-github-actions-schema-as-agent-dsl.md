---
title: "The GitHub Actions workflow schema as an agent-harness DSL"
date: 2026-10-30
status: research
sources_verified: true
---

# The GitHub Actions workflow schema as an agent-harness DSL

## TL;DR

- The schema is **not one artifact**: the authoritative parser + `workflow-v1.0.json` template schema live in `actions/languageservices` (MIT, GitHub, "not taking contributions"); the community JSON Schema lives in SchemaStore (Apache-2.0). Both are permissive and stable, but GitHub alone decides the grammar.
- Three independent executors already run the schema outside github.com: `nektos/act` (MIT, v0.2.92, 2026-10-28), Gitea/Forgejo `act_runner` (MIT, v5.2.4, 2026-10-28; "familiarity, not compatibility"), and `ChristopherHX/runner.server` (MIT), which re-implements the Actions *service* so the official `actions/runner` (MIT) can be driven by a non-GitHub control plane. Argo/Tekton converters are toy-grade.
- **GitHub Agentic Workflows (`github/gh-aw`, MIT, v1.0.1 on 2026-10-27)** is the closest prior art: Markdown + frontmatter compiled into a `.lock.yml` Actions workflow, agent job read-only and sandboxed, writes via "safe-outputs" jobs, approval via environment protection rules. It proves the idea works but inherits every CI limit (20-minute default agent timeout, 6 h job cap, 35-day run cap, environments only on paid/public plans).
- The schema cannot express loops, dynamic fan-out beyond a 256-job `matrix`, per-step retries, long waits, signals, or memory between runs. Every workaround (re-runs, `workflow_dispatch`, `repository_dispatch`, environments with required reviewers) depends on the GitHub control plane.
- **Recommendation:** adopt the schema **as the authoring/import format**, add a namespaced `x-agent:` extension for the missing semantics, validate with `@actions/workflow-parser` + `actionlint`, and compile to a Temporal interpreter (jobs → child workflows, steps → activities, `uses:` → act's action runner inside an ARC-style ephemeral pod). Do not try to make the raw schema the runtime model.

## Governance and licence table

| Project | Role | Licence | Governance | Latest verified version / date |
|---|---|---|---|---|
| SchemaStore `github-workflow.json` | Community JSON Schema (draft-07) | Apache-2.0 | Community (SchemaStore) | rolling, `master` (2026-10) |
| `actions/languageservices` (`@actions/workflow-parser`, `@actions/expressions`, `@actions/languageservice`) | Official TS parser, expression evaluator, LSP | MIT | GitHub, single vendor; repo states "not taking contributions" | npm `@actions/workflow-parser` 0.3.x (2026) |
| `actions/runner` | Official runner (Runner.Listener/Worker) | MIT | GitHub, single vendor | v2.338.2 (2026-10-26) |
| `actions/actions-runner-controller` (ARC) | Runner autoscaler on K8s | Apache-2.0 | GitHub (since 2023); legacy CRDs community-maintained | 0.15.0 (2026-10-01) |
| `nektos/act` | Local executor | MIT | Independent OSS (nektos), 72.5k stars | v0.2.92 (2026-10-28) |
| Gitea `act_runner` / Forgejo `forgejo-runner` | Executor for Gitea/Forgejo Actions, forks of act | MIT | Gitea Ltd / Forgejo (Codeberg e.V.) | act_runner v5.2.4 (2026-10-28) |
| `ChristopherHX/runner.server` | Unofficial re-implementation of the Actions service + runner fork | MIT | Individual maintainer | active, 2.3k commits (2026) |
| `rhysd/actionlint` | Static checker, Go library | MIT | Individual maintainer | v1.7.12 (2026-03-30) |
| `github/gh-aw` | Agentic Workflows compiler/CLI extension | MIT ("Copyright GitHub, Inc.") | GitHub Next, single vendor | v1.0.1 (2026-10-27) |
| `LinuxSuRen/github-action-workflow` | GH Actions → Argo Workflows converter | MIT | Individual, 7 stars | experimental |
| `jenkins-x-plugins/jx-tekton-to-actions` | Tekton → GH Actions (reverse) | Apache-2.0 | Jenkins X (CDF) | low activity |
| Argo Workflows | K8s-native DAG engine | Apache-2.0 | CNCF graduated (Argo, 2022-12-06) | v4.1.6 (2026-10-22) |
| Tekton Pipelines | K8s-native CI/CD engine | Apache-2.0 | CDF graduated 2022-11 → CNCF incubating (2026-03-25) | v1.18.0 (2026-10-29) |
| Temporal | Durable execution | MIT (server) | Temporal Technologies, single vendor | already in Forjate |
| Dagger `dagger-for-github` | Action that calls Dagger Functions on a runner | Apache-2.0 | Dagger Inc. | v6 |
| Woodpecker CI | Own YAML (Drone lineage) | Apache-2.0 | Community | contrast only |

All items are MIT or Apache-2.0, so licence is not a blocker anywhere. Governance is: only Argo and Tekton are foundation-governed; everything that defines or executes the GitHub schema is controlled by GitHub or individuals.

## 1. The schema itself

**Where it lives.** There are two schemas with different authority:

- The **official** one is the template schema `workflow-v1.0.json` inside `actions/languageservices/workflow-parser`. `parseWorkflow()` reads YAML into an intermediate representation and validates it against that schema; `convertWorkflowTemplate()` produces a `WorkflowTemplate` object with jobs and steps. The same repo ships `@actions/expressions` (parser + evaluator for `${{ }}`) and the language server used by the VS Code extension. MIT, published to npm, but the README says the maintainers are "not taking contributions" (security fixes only). An older Go `actions/workflow-parser` exists but the GitHub URL now 404s; treat it as gone.
- The **community** one is SchemaStore's `github-workflow.json` (draft-07, Apache-2.0). It is what editors use for autocompletion via `yaml-language-server` and what `check-jsonschema` validates. It lags GitHub's changes by days to weeks and encodes GitHub's documentation, not GitHub's parser.

**Stability.** The grammar has been backward compatible since 2019 (`on / jobs / steps / uses / with / needs / if / strategy.matrix / outputs`). Additions are rare and additive: the `case()` expression function (early 2026, actionlint 1.7.11 added support 2026-02-14), `on.schedule.timezone` (actionlint 1.7.12, 2026-03-30). No versioning field exists in the YAML; "v1.0" is only the internal template name.

**Expression language.** `${{ }}` has a fixed set of 13 functions (`contains`, `startsWith`, `endsWith`, `format`, `join`, `toJSON`, `fromJSON`, `hashFiles`, `case`, `success`, `always`, `cancelled`, `failure`), comparison and boolean operators, literals and context access. No user-defined functions, no iteration, no arithmetic. Contexts (`github`, `env`, `vars`, `job`, `jobs`, `steps`, `runner`, `secrets`, `strategy`, `matrix`, `needs`, `inputs`) are scoped per key; e.g. `secrets` is unavailable in `if:` of a step. The semantics are implementable: `@actions/expressions` (TS) and act's `pkg/exprparser` (Go) both do it.

**Composition.** `uses:` has three step forms (`{owner}/{repo}@{ref}`, `./local/path`, `docker://image`) and two job forms for reusable workflows (`{owner}/{repo}/.github/workflows/{file}@{ref}`, `./.github/workflows/{file}`). Reusable workflows can chain up to ten levels; "loops in the workflow tree are not permitted"; secrets do not cascade automatically; `env` from the caller is not propagated. Composite actions (`runs.using: composite`) are the step-level reuse unit. Resolution of `{owner}/{repo}` is implicit against github.com, which is the first non-portable assumption an external executor must replace.

**What the schema cannot express for an agent harness.**

| Need | Schema support | Workaround on GitHub |
|---|---|---|
| Loops / "until done" | None; DAG only | Re-run, cron, workflow chaining via `workflow_run`/`repository_dispatch` |
| Dynamic fan-out | `matrix` with `fromJSON()`, hard cap 256 jobs/run | Split runs; nested reusable workflows |
| Human approval gate | None at step level | `environment:` with required reviewers (max 6, 30-day wait cap; needs public repo or Team/Enterprise) or `manual-approval` as gh-aw does |
| Long waits | None; job ≤ 6 h hosted (5 d self-hosted), run ≤ 35 d | Wait timer on environments, split into separate runs |
| Retry with backoff per step | None (`continue-on-error`, `timeout-minutes` only) | Shell loops or `nick-fields/retry` action |
| State/memory between runs | None | Artifacts, cache, `vars`, external store |
| Signals / external events into a running workflow | None | `repository_dispatch`, `workflow_dispatch` start *new* runs only |
| Compensation / saga | None | Manual |

## 2. Third-party executors

**nektos/act** (MIT, v0.2.92 on 2026-10-28, three releases that day for security hardening). Mature as a local runner; runs each job in Docker, resolves `uses:` by cloning from github.com, evaluates expressions and matrices. The project's own "not supported" page lists: `concurrency`, `run-name`, `GITHUB_STEP_SUMMARY`, problem matchers/annotations, incomplete `github` context, job-level `permissions`, `timeout-minutes`, `continue-on-error`, step cancellation, OIDC. Its Go packages (`pkg/model` with `Workflow`, `Job`, `Step`, a `planner`; `pkg/runner`; `pkg/exprparser`) are importable and are the closest thing to a "GH Actions YAML → DAG" library in Go; Gitea built on exactly this.

**Gitea Actions / Forgejo Actions.** `act_runner` (MIT, v5.2.4, 2026-10-28) embeds a fork of act (`gitea/act`) and talks to the Gitea server over HTTP (Connect/gRPC-style ping/fetch-task). Forgejo documents its stance explicitly: "strives for familiarity instead of compatibility"; job-level `permissions` and `continue-on-error` are ignored, parts of the `github` context are missing, OIDC uses a different key, default image is Debian with Node only. Important precedent: a second control plane re-implemented the *server* side so that the YAML stays recognisable but the runtime is its own.

**actions/runner** (MIT, v2.338.2, 2026-10-26). Runner.Listener long-polls the Actions service for jobs; Runner.Worker executes them. It has no documented way to point at a non-GitHub control plane, but `ChristopherHX/runner.server` (MIT) proves it is possible: it re-implements the Actions service protocol (job queue, artifacts, cache, OIDC, callable workflows, matrix evaluation) and the unmodified runner registers against it. That is a viable, if single-maintainer, route to reuse real GitHub runners with a Forjate scheduler.

**Parsers/validators.** `@actions/workflow-parser` (TS, official), act `pkg/model` (Go), `actionlint` (Go library and CLI, type-checks `${{ }}`, validates action inputs/outputs by fetching `action.yml`, reusable-workflow I/O, runner labels, cron, shellcheck/pyflakes). No maintained Python parser of equivalent depth was found.

**Dagger.** `dagger-for-github` is only an action that runs Dagger Functions on a runner; Dagger does not execute Actions YAML. Woodpecker (Apache-2.0) and Drone use a different, flatter pipeline schema and are irrelevant except as evidence that "YAML CI DSL in Kubernetes" has been done many times.

## 3. GitHub Agentic Workflows (gh-aw)

`github/gh-aw` (MIT, GitHub Next, v1.0.0 on 2026-10-26, v1.0.1 on 2026-10-27, versions 0.83.3-0.85.4 retired for a security issue) is a `gh` CLI extension. A workflow is a Markdown file: YAML frontmatter (`on`, `permissions`, `engine`, `tools`, `mcp-servers`/`mcp-scripts`, `safe-outputs`, `network`, `roles`, `runs-on`, `timeout-minutes`, `max-turns`, `max-ai-credits`, `concurrency`) plus a natural-language body. `gh aw compile` validates and emits `.github/workflows/<name>.lock.yml`, a plain Actions workflow that GitHub executes.

**Compile mapping.** The compile step is a template expander: the body becomes the prompt file; `engine:` selects a container/CLI step (Copilot, Claude Code, Codex, Gemini, Pi); `tools:` and `mcp-servers:` become an MCP gateway (v0.5.0 in 0.93.6) configuration and a firewall (v0.29.0) that implements `network:` allowlists; `safe-outputs:` becomes additional jobs. Approval is `on.manual-approval: <environment>`, i.e. an environment protection rule, not a workflow primitive. `roles:` (default `[admin, maintainer, write]`, exact match) is compiled into a job that checks the actor's repo permission. `stop-after:` deadlines and `command:` slash triggers are compiled into `if:` guards over comment events.

**Security model.** The agent job runs with read-only `permissions` and sandboxed network. It "cannot invoke GitHub APIs directly - it only generates these declarative requests": structured JSON lines (`create_issue`, `add_comment`, `create_pull_request`, `dispatch_workflow`, 40+ handlers including Jira/ADO/Linear) that a separate job with minimal scoped permissions validates (sanitisation, mention normalisation, `max` per type, dedup, `required-labels`, fork/cross-repo allowlists, "threat detection" rules `CTR-###`) and applies. This is exactly the harness-level separation Forjate wants between UI/intent and privileged execution, and it is implemented entirely with jobs, `needs:` and `permissions:`.

**Where it runs, lock-in.** `runs-on` defaults to `ubuntu-latest` and framework jobs to `ubuntu-slim` (GitHub-hosted). Self-hosted runners work via `runs-on`, with caveats on service-container networking. Default agent `timeout-minutes` is 20; `max-turns` 500. The Copilot engine requires a Copilot subscription and the Copilot CLI; the compiled lock file depends on `github/gh-aw` actions and GitHub-only features (environments, `GITHUB_TOKEN`, Actions API). Copilot coding agent likewise runs in "its own ephemeral development environment, powered by GitHub Actions" (Ubuntu x64 only, `copilot-setup-steps.yml`), billed against Actions minutes. GitHub Next frames all of this as **Continuous AI**: "all uses of automated AI to support software collaboration", usually "scripted agent-like AI workflows with human oversight" rather than autonomous agents. The pattern is portable; the artefacts are not.

## 4. Mapping to Kubernetes-native engines

| GH Actions | Argo Workflows (v4.1, 2026) | Tekton Pipelines (v1.18, 2026) | Temporal interpreter |
|---|---|---|---|
| `jobs.<id>` | `dag.tasks[]` / `steps` template | `pipeline.tasks[]` (Task = Pod) | child workflow per job |
| `needs:` | `dependencies` / `depends` (enhanced, supports `.Succeeded/.Failed`) | `runAfter`, `when` | `await` on futures |
| `steps[]` | containers in sequence (`steps` template) or one container | `steps[]` in a Task (sequential containers in one Pod) | activities, sequential |
| `strategy.matrix` | `withItems` / `withParam` (unbounded fan-out) | `matrix` (beta) | fan-out loop over child workflows |
| `if:` | `when` expressions (expr) | `when` guards | plain code |
| `outputs` | `outputs.parameters`, artifacts | `results` | return values |
| `environment` + reviewers | `suspend` template + `argo resume` | none (custom task / Pipelines-as-Code) | signal + timer (Temporal's native strength) |
| retries | `retryStrategy` with backoff | `retries` (count only) | per-activity retry policy with backoff |
| `uses: owner/repo@ref` | none | Tekton Hub/catalog has different tasks | act's action runner as an activity |

Converters: `LinuxSuRen/github-action-workflow` (MIT) converts to Argo and works as an Argo CD CMP, but "only the first job could be recognized in each file" and `uses:` is limited to four hard-coded actions. `jx-tekton-to-actions` goes the other way. No maintained GH Actions → Tekton tool was found. Conclusion: the mapping is straightforward conceptually, but executing `uses:` steps is the hard part and only act has solved it.

**Temporal interpreter.** A generic `GhaWorkflow` Temporal workflow receives the parsed `WorkflowTemplate`, topologically sorts jobs by `needs`, starts each as a child workflow (expanding `matrix` to N children), evaluates `if:` with an expressions library, and runs each step as an activity whose worker launches an ephemeral Kubernetes pod (same pattern as ARC's `EphemeralRunner`) executing `run:` or an action via act's runner library. Everything the schema lacks (signals for approval, timers for waits, retry policies, memory in workflow state, loops via `continueAsNew`) is native to Temporal, which is why the extension layer should map onto Temporal concepts rather than Argo's.

## 5. Self-hosted runners on Kubernetes (ARC)

`actions/actions-runner-controller` (Apache-2.0) is official under the `actions` org; 0.15.0 (2026-10-01) adds in-place patch upgrades, configurable `terminationGracePeriodSeconds`, QPS and `max-concurrent-reconciles` tuning and faster ephemeral-runner deletion. Supported mode is the Helm charts `gha-runner-scale-set-controller` + `gha-runner-scale-set` with CRDs `AutoscalingRunnerSet`, `EphemeralRunnerSet`, `EphemeralRunner` (plus `AutoscalingListener`). The listener pod long-polls the GitHub Actions service for job demand and the controller creates one pod per job. The legacy `RunnerDeployment`/`HorizontalRunnerAutoscaler` CRDs are "maintained by the community only". ARC cannot be pointed at a non-GitHub scheduler: the listener speaks the Actions service protocol. The reusable idea is the **EphemeralRunner pattern** (one pod per job, registered just-in-time, deleted on exit), which a Forjate harness can replicate with its own CRD or with Temporal workers that create pods.

## 6. Fit assessment

**Pros.** Universally known; every LLM writes it fluently (a real advantage for an AI-assisted builder); first-class tooling exists and is permissively licensed (`@actions/workflow-parser` for the UI/builder, `actionlint` for validation, SchemaStore for editor autocompletion); thousands of actions become candidate steps; gh-aw demonstrates that agent prompts, tools, MCP and safe-outputs fit into the model; the `needs:`/`matrix`/`outputs` graph is exactly the DAG a builder should iterate on before wiring code.

**Cons.** Designed for finite CI jobs: no loops, waits, signals, retries, state or approvals as schema primitives. `uses:` steps assume a GitHub-shaped runner (Node runtime, `GITHUB_*` env, `github` context, github.com resolution, `GITHUB_TOKEN`). The expression language is intentionally weak. GitHub controls the grammar unilaterally and its reference parser accepts no contributions. Argo/Tekton executors would re-implement act poorly; using act directly brings Docker-in-pod requirements.

**Recommendation: extend with a namespaced `x-agent:` extension, compile to Temporal.** Use the schema as-is for everything it already covers so files remain valid for `actionlint`, the VS Code extension and `act` (unknown top-level keys under `jobs.<id>` and `steps[]` are rejected by the official parser, so the extension must live in a place the parser tolerates: top-level `x-agent:` keyed by job/step id, or `env`-free metadata inside `with:` of a dedicated `forjate/agent@v1` action). Compile with `@actions/workflow-parser` in the UI tier, run an interpreter workflow in Temporal, and use act's library in an ephemeral pod to execute third-party `uses:` steps. Treat gh-aw as a competitor-compatible import target (its frontmatter maps to `x-agent:` almost 1:1), not as a runtime.

```yaml
name: triage-and-fix
on:
  repository_dispatch:
    types: [issue.labeled]
  workflow_dispatch:
    inputs: { issue: { type: number, required: true } }

jobs:
  plan:
    runs-on: forjate-agent
    permissions: { contents: read, issues: read }
    outputs:
      tasks: ${{ steps.plan.outputs.tasks }}
    steps:
      - uses: actions/checkout@v5
      - id: plan
        uses: forjate/agent@v1
        with:
          engine: claude-code
          prompt: Read issue ${{ inputs.issue }} and emit a JSON list of fix tasks.
          mcp-servers: [github-readonly]
          output-schema: schemas/tasks.json

  fix:
    needs: plan
    runs-on: forjate-agent
    strategy:
      matrix:
        task: ${{ fromJSON(needs.plan.outputs.tasks) }}
    steps:
      - uses: actions/checkout@v5
      - uses: forjate/agent@v1
        with: { engine: claude-code, prompt: "Implement ${{ matrix.task.title }}" }
      - run: make test

  review:
    needs: fix
    environment: human-review          # standard key; harness maps it to a signal gate
    steps:
      - uses: forjate/safe-output@v1
        with: { type: create-pull-request, max: 1 }

x-agent:                               # Forjate extension, ignored by GitHub/act
  jobs:
    plan:
      retry: { max-attempts: 3, backoff: exponential, initial-interval: 30s }
      memory: { namespace: triage, key: issue-${{ inputs.issue }} }
    fix:
      loop: { until: "steps.test.outcome == 'success'", max-iterations: 5 }
      fan-out: { max-parallel: 20, unbounded: true }
    review:
      gate: { kind: signal, name: approve, timeout: 14d, on-timeout: cancel }
  budget: { max-turns: 200, max-ai-credits: 500 }
```

## Gaps

- The runner-protocol re-implementation (`runner.server`) is a one-person project; relying on it for production would need forking or a clean-room protocol document, which GitHub does not publish.
- Not measured: how many popular actions actually run under act outside GitHub (Node 20/24 runtime, `GITHUB_TOKEN` usage, `@actions/core` outputs). A sample of the top 50 Marketplace actions should be tested.
- gh-aw's `.lock.yml` output was not diffed against its source in this research; the mapping description comes from its reference docs.
- Forgejo's incompatibility list is self-described as incomplete.
- Whether GitHub's language server tolerates unknown top-level keys (`x-agent:`) without red squiggles needs an empirical check; SchemaStore's schema sets `additionalProperties: false` at the root in some revisions.
- Fetch tooling rendered some release years ambiguously (runner v2.338.2, Tekton v1.18.0); versions are correct, dates inferred from sequence and should be re-checked before quoting externally.

## Sources

- SchemaStore github-workflow.json: https://github.com/SchemaStore/schemastore/blob/master/src/schemas/json/github-workflow.json ; LICENSE: https://github.com/SchemaStore/schemastore/blob/master/LICENSE
- actions/languageservices: https://github.com/actions/languageservices ; workflow-parser README: https://github.com/actions/languageservices/blob/main/workflow-parser/README.md ; npm: https://www.npmjs.com/package/@actions/workflow-parser
- GitHub Docs, expressions: https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
- GitHub Docs, workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Docs, limits: https://docs.github.com/en/actions/reference/limits
- GitHub Docs, environments: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- GitHub Docs, reusable workflows: https://docs.github.com/en/actions/how-tos/sharing-automations/reuse-workflows
- nektos/act: https://github.com/nektos/act ; releases: https://github.com/nektos/act/releases ; unsupported: https://nektosact.com/not_supported.html ; model package: https://github.com/nektos/act/tree/master/pkg/model
- Gitea act_runner: https://gitea.com/gitea/act_runner
- Forgejo Actions vs GitHub Actions: https://forgejo.org/docs/next/user/actions/github-actions/
- actions/runner: https://github.com/actions/runner ; releases: https://github.com/actions/runner/releases
- ChristopherHX/runner.server: https://github.com/ChristopherHX/runner.server
- rhysd/actionlint: https://github.com/rhysd/actionlint ; releases: https://github.com/rhysd/actionlint/releases
- github/gh-aw: https://github.com/github/gh-aw ; LICENSE: https://github.com/github/gh-aw/blob/main/LICENSE ; releases: https://github.com/github/gh-aw/releases ; about: https://github.github.com/gh-aw/about/ ; frontmatter: https://github.github.com/gh-aw/reference/frontmatter/ ; safe-outputs: https://github.github.com/gh-aw/reference/safe-outputs/ ; triggers: https://github.github.com/gh-aw/reference/triggers/
- GitHub Next, Continuous AI: https://githubnext.com/projects/continuous-ai/
- Copilot coding agent: https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent ; environment: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment
- actions-runner-controller: https://github.com/actions/actions-runner-controller ; 0.15.0 changelog: https://github.blog/changelog/2026-10-01-actions-runner-controller-release-0-15-0
- LinuxSuRen/github-action-workflow: https://github.com/LinuxSuRen/github-action-workflow
- jx-tekton-to-actions: https://github.com/jenkins-x-plugins/jx-tekton-to-actions
- Argo Workflows releases: https://github.com/argoproj/argo-workflows/releases ; DAG docs: https://argo-workflows.readthedocs.io/en/latest/walk-through/dag/ ; CNCF graduation: https://www.cncf.io/announcements/2022/12/06/the-cloud-native-computing-foundation-announces-argo-has-graduated
- Tekton blog (CNCF incubation 2026-03-25, v1.17.0): https://tekton.dev/blog/ ; releases: https://github.com/tektoncd/pipeline/releases ; CDF graduation: https://tekton.dev/blog/2022/10/26/tekton-graduation/
- Temporal LICENSE: https://github.com/temporalio/temporal/blob/main/LICENSE
- Dagger GitHub integration: https://docs.dagger.io/integrations/github-actions
- Woodpecker CI: https://github.com/woodpecker-ci/woodpecker

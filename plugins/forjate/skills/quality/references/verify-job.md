# The verify Job

`ephemeral.sh up <name>` blocks until the verify Job exits 0. That exit code is the Crawl gate (`G-Q-1`), so the Job proves the stage, not that the Pods are up.

## What it proves

| Assertion | Why | Source |
|-----------|-----|--------|
| every pipeline `verify_assertions` line | the pipeline expert named what landing correctly means | `decisions/data-pipeline.yaml` |
| the KPI measured once on the seed, printed as `KPI <kpi_metric>=<value>` | the business gate `G-BIZ-1` needs the number; a parseable line lets the coordinator and CI read it | `decisions/business.yaml` |
| the seed's exceptions went through the exception path (review queue row, escalation record, dead letter) | the happy path proves nothing about the 20 % the business cares about | pipeline `seed_size`, business `as_is_exceptions` |
| a second run changes nothing (same counts, no duplicate rows, no second post) | idempotency is how Walk survives retries | pipeline `idempotency_key`, `replay` |
| no write reached a system of record without an approval token | the AI-engineering tool gate and the security write gate, proven, not asserted | `tool_write_gate`, `tools` |
| logs of model calls carry the data class and not the payload (one grep) | the security record's `audit_log_content` | `decisions/security.yaml` |
| exit non-zero on any miss, with the failing assertion named in the log | `up` must fail loudly | |

Each line goes in `settings.verify_assertions`; the Job's script is the app-scaffold's to write from that list, the kustomize skill wires the Job.

## Shape

From the kustomize skill's lifecycle Job pattern: `suspend: true`, `backoffLimit: 0`, `ttlSecondsAfterFinished`, `restartPolicy: Never`, restricted-compatible security context, requests and limits, `envFrom` the component Secrets by their mounted names. It reads endpoints from `usecase.yaml` (`<service>.uc-<name>.svc.cluster.local:<port>`) and nothing else; a verify Job that reaches outside the namespace at Crawl is a finding.

Name: the plan's `check.ref` for `G-Q-1`, or `<prefix>-validate`. The same name goes in `usecase.yaml` `spec.jobs.verify`; CI asserts it exists in the built manifest.

## Walk and Run

The Job keeps running on every deploy (ArgoCD PostSync hook or a CronJob) against the live environment with a synthetic canary item, so the Crawl proof becomes a continuous check; the `metric` gates read from the application table or Prometheus instead of the Job log. State in `rationale` which assertions move from the Job to a metric at Walk and which stay in the Job.

## Anti-patterns

- `kubectl wait --for=condition=ready` as the whole verify: a readiness probe with a Job's name.
- Assertions on the seed only (`count == 20`) without the exception path.
- A Job that writes to the system of record to "test" it.
- A KPI computed by the model itself.
- Catching every error and exiting 0 "so the demo passes".

# Design: the scaffold as a walking skeleton (#44)

Status: design, 2026-11-15. Implements issue #44. Unblocks #46 part 1 and #40.

## Why

The #28 cold start showed that app-scaffold writes the whole Crawl app. For invoice-intake that was 48 files, 3,547 lines of `src` and 104 unit tests. The app-scaffold suite then wrote 153 to 223 tests per run, at 155 turns (the cap was 150), 30 min and 7 to 9 USD per run. Even so, it stopped at Crawl's workloads: invoice-intake's record names `cron-job`, `posting-worker` and `review-api` at Walk, and none of them exist. In G1, app-scaffold was the most expensive agent at 18.83 USD.

Business code does not fit in one builder run, and an assembler should not write it. What every stage needs is the skeleton. So the work splits the way a tech lead and an architect would split it:

- **The scaffold, which stays minimal**: every workload of every stage in scope gets an entry point. Every store, queue, model route and external system is wired through a seam that has a contract, and the verify Job proves the route end to end. A diagram shows how the parts connect.
- **The backlog, which comes after the scaffold**: a deterministic step turns the seams, the pending assertions and the workarounds into tickets. Each ticket links to its record and its gate. An agent team picks the tickets up during Walk.

## Files that change

| File | Change |
|------|--------|
| `scripts/builder/schemas/scaffold.schema.json` | `workloads[].stage` and `tools[].stage` (`crawl`, `walk` or `run`; the default is `crawl`). An optional `spec.skeleton` block with `diagram`, `seams`, `verify` and `workarounds`. |
| `scripts/builder/schemas/backlog.schema.json` (new) | `kind: Backlog`, the tickets. |
| `scripts/builder/backlog.py` (new) | The post-scaffold step: scaffold, records and gates go in, `.builder/backlog.yaml` and `.builder/backlog.md` come out. It is deterministic and never names a component. |
| `scripts/builder/validate.py` | Validates `backlog.yaml` when it exists. Its tickets must name existing seams and gates. |
| `scripts/builder/scaffold-check.py` | When `spec.skeleton` exists, it runs the skeleton checks below. Without the block, the scaffold is a legacy full app and only the old checks run. That covers the two goldens until #46 regenerates them. |
| `skills/kustomize/scripts/assemble.py` | The Crawl root wires only `stage: crawl` workloads. `stages/walk` and `stages/run` add the workloads of their own stage. |
| `skills/app-scaffold/` | The skill and its references are rewritten around the skeleton. Domain unit tests are gone. Seams, the diagram and the workaround notes are added. |
| `skills/coordinator/` | Runs `backlog.py` after the scaffold. The report gains a Backlog section. |
| `skills/stage-planner/references/stage-defaults.md`, `plan.md` | Walk closes with a minimal implementation, and the agent team is a Walk capability. |
| `evals/app-scaffold/evals.json` | Skeleton assertions and a size budget replace the domain assertions. |

## Schema: the stage a workload belongs to

```yaml
workloads:
  - {name: worker,         kind: job,        phase: run, stage: crawl, command: [...]}
  - {name: posting-worker, kind: deployment, stage: walk, port: 8000, health_path: /healthz, command: [...]}
tools:
  - {name: post_invoice, module: invoice_intake/tools/post_invoice.py, flags: [idempotent, requires approval token], stage: walk}
```

A workload's `stage` is the first stage whose architecture record lists it. The same rule applies to a tool and the AI-engineering record. A workload listed at Crawl and again at Walk is `crawl`, because stages accumulate. The assembly reads this field, and nothing else decides where a workload lands.

## The skeleton contract

```yaml
skeleton:
  diagram: app/docs/connections.md          # a Mermaid graph: every workload, store, queue, model route and system
  seams:
    - id: erp-posting                       # stable, used by the code marker and the ticket
      kind: system                          # tool | model | store | queue | system | surface | workload
      name: post_invoice
      stage: walk
      record: decisions/ai-engineering.yaml # the record that specifies it
      contract: invoice_intake/tools/post_invoice.py
      double: odoo-stub                     # what stands in for it at Crawl
      status: wired                         # wired: the call goes through the transport, the double decides; stub: raises NotImplementedError
      gates: [G-AI-2]                       # the gates.yaml ids it serves
  verify:
    job: invoice-intake-verify
    pending:                                # quality assertions whose truth needs business logic
      - {assertion: "15 matched, 3 mismatched ...", seams: [po-matching]}
  workarounds:
    - {seam: shared-postgres, problem: "the bundle recomposes the database the records chose", workaround: "one server, a role per engine; see README"}
```

**A seam with a contract** has four parts:

1. A typed signature. The record's flags become code: the approval-token refusal before any I/O, the idempotency key, the bounds, the policy hook and the structured log line.
2. A real transport to the store, the double or the stub.
3. A decision delegated to the double. In replay mode the seed's labels decide; in rules mode a rule set decides.
4. A `# SEAM <id>: <what the business rule will do> (backlog)` marker where the business rule will go.

**The verify Job** does three things:

- It prints `[PASS] connected: <seam-id>` for every Crawl seam it drove end to end.
- It runs every record assertion that the skeleton makes true: idempotency on a second run, no write without a token, no payload in the logs, the KPI line computed from what the doubles decided.
- It prints `[PENDING] <assertion> -> backlog` for each assertion that needs business logic.

A pending assertion does not fail Crawl. With `VERIFY_STRICT=1`, which the Walk overlay sets, it does fail. That is how Walk's exit criterion "minimal implementation" becomes a check.

**What the scaffold does not write**: domain functions beyond what a passing route needs, and domain unit tests. The tests that remain are `tests/test_contract.py`, which checks that the tool signatures match the record, that the approval refusal happens, that a bound stops the loop and that `scaffold.yaml` validates. They also include the eval, injection and redaction markers when the records name them. Those run through the double, so the gates runner's `app-tests`, `eval-regression`, `injection-suite` and `redaction-check` keep working.

**scaffold-check, when `spec.skeleton` exists**, checks that:

- every architecture workload of every stage in scope has a scaffold workload of that `stage`;
- every seam has its `SEAM <id>` marker under `app/src`;
- every tool is a seam, and every Deployment is either a seam or a seam's double;
- the diagram exists and names every workload and every seam;
- the verify module names every Crawl seam it connects;
- every pending assertion names existing seams;
- every seam's `gates` exist in `gates.yaml`.

The size budget (files, lines, test count) lives in the eval assertions, not in the checker. A threshold in a gate is a number that someone will raise later.

## The backlog

`backlog.py <usecase-dir>` writes `.builder/backlog.yaml`, which follows `backlog.schema.json`, and renders `.builder/backlog.md`:

```yaml
apiVersion: forjate.io/v0
kind: Backlog
metadata: {usecase: invoice-intake, version: 1}
spec:
  tickets:
    - id: T-erp-posting
      kind: seam                       # seam | workload | assertion | workaround | open
      title: "Implement post_invoice: create one payable in Odoo"
      stage: walk
      seam: erp-posting
      record: decisions/ai-engineering.yaml#stages.walk.settings.tools
      contract: app/src/invoice_intake/tools/post_invoice.py   # marker SEAM erp-posting
      gates: [G-AI-2]
      acceptance: ["the gate texts", "the pending assertion texts naming this seam"]
      depends_on: []
```

Tickets come from four sources:

- one per seam;
- one per Walk or Run workload whose entry point is still a skeleton;
- one per pending assertion that no seam ticket covers;
- one per workaround and one per `OPEN:` note.

When a seam names no `gates`, the gates come from those of the record's owner area at the transition out of the seam's stage. Ids are stable, so running the step again rewrites the same tickets.

## Walk

The Walk exit criteria become:

- the verify Job passes with `VERIFY_STRICT=1`;
- every Walk ticket is closed;
- that is the minimal implementation.

The agent team that closes the tickets is a Walk capability, listed in the stage model next to ArgoCD and Sealed Secrets. Run hardens what Walk implemented. It does not finish the code.

## Open questions for the owner

Asked on the ledger. Each one lists the recommended option first.

1. Backlog as files in the repo (`.builder/backlog.yaml` plus `.md`), with a GitHub export left as a follow-up, versus GitHub issues straight away.
2. The scope of a stub with a contract and of the verify Job: the `[PENDING]` and `VERIFY_STRICT` split above, versus keeping every quality assertion strict at Crawl.
3. The Walk exit criteria as above: strict verify plus closed Walk tickets, with the agent team as a Walk capability.

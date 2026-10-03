# Consolidating gates.yaml

`.builder/gates.yaml` is the one file an approver reads before unlocking a stage. Schema: `${CLAUDE_PLUGIN_ROOT}/scripts/builder/schemas/gates.schema.json`.

## Shape

```yaml
apiVersion: forjate.io/v0
kind: Gates
metadata: { usecase: invoice-intake, version: 1 }
spec:
  transitions:
    crawl->walk:
      approver: finance ops lead
      gates:
        - { id: G-Q-1, text: verify Job exits 0 on the seeded set of 20 PDFs with 3 mismatches, owner: quality, check: { type: verify-job, ref: inv-validate } }
        - { id: G-BIZ-1, text: straight-through rate measured on the sample and the CFO has seen the number, owner: business, check: { type: metric, ref: straight_through_rate } }
        - { id: G-DS-1, text: retention of PoC data decided, owner: data-store, check: { type: manual, ref: decisions/data-store.yaml } }
    walk->run:
      approver: CFO
      gates:
        - { id: G-SEC-1, text: namespace default-deny with egress allow-list to Odoo and IMAP only, owner: security, check: { type: ci, ref: netpol-check } }
        - { id: G-COMP-2, text: DPO approves the DPIA, owner: compliance, check: { type: manual, ref: the DPIA } }
  pack_overrides:
    - { rule: "pack:regulated-corp#SEC-1", overridden_by: "pack:solo-dev#SEC-1", reason: "user pack relaxes PSA to baseline at Walk; corporate rule says restricted" }
```

## Algorithm

1. **Collect.** For every `decisions/*.yaml`: gates under `stages.crawl.gate_to_next` go to `crawl->walk`; under `stages.walk.gate_to_next` to `walk->run`; under `stages.run.gate_to_next` nowhere (there is no transition out of Run; keep them in the record). Then the plan's `exit_criteria` per stage, for ids no record repeated. Owner is the record's area (or the exit criterion's `owner`).
2. **Verbatim.** Ids and texts are copied, not rephrased. A record's language is the brief's; so is the file's.
3. **Collisions.** One id, two different texts across records. The id pattern allows no suffix, so: keep the first by file order under its id, add the second under the next free id of the same family (`G-SEC-9`) with its text prefixed `CONFLICT with G-SEC-1 (devops):`, and raise an open question in your own record naming both records and both texts. The authors resolve it; you make it impossible to miss.
4. **Checks.** A gate without a `check` is manual by schema. Give each one a type and a ref:

| `check.type` | `ref` convention | Examples |
|--------------|------------------|----------|
| `verify-job` | the Job name in `usecase.yaml` | `inv-validate`, `dbmig-validate` |
| `ci` | a workflow or check name | `validate-usecases` (contract and Job presence), `validate-kustomize` (build and kubeconform), `validate-builder` (records and packs), `netpol-check`, `psa-check`, `secret-scan`, `env-example-check`, `argocd-revision-check`, `eval-regression`, `injection-suite`, `licence-inventory`, `rotation-rehearsal`, `restore-rehearsal`, `stage-overlay-builds` |
| `metric` | the metric name, the same as the business `kpi_metric` or a signal from the quality record | `straight_through_rate`, `resolved_without_human_rate`, `job_duration_seconds` |
| `manual` | the document the signer reviews | `decisions/compliance.yaml`, `.builder/report.md`, `the DPIA`, `the Walk report` |

Mapping rules: a text that names a Namespace label, a NetworkPolicy, a secret mechanism, a tag, a signature-free property of the manifests is `ci`; a text that names a rate or a duration is `metric`; a text that names the verify Job or "seeded" is `verify-job`; a text that names a person signing, approving or deciding is `manual`, and its text must name the role. Do not downgrade a `ci`-able gate to `manual` because the check does not exist yet; keep it `ci` and list the missing check in your record's `risks`.

5. **Approver.** `approver` per transition from the business record's `approver` setting at the stage being left; absent means the brief's approver.
6. **Overrides.** For every role with a record, run the resolver and copy each entry under `overrides` where the overridden rule was a `must` into `pack_overrides` with a reason; also any record whose `rationale` reports an override. An empty list is valid and means none.
7. **Scope.** No transition into a stage the plan skipped (`in_scope: false`); if Run is out of scope there is no `walk->run`.
8. **Report.** Automated versus manual count per transition, collisions, overrides, roles the plan runs with no record yet (the coordinator prints these).

## What the validator checks

Schema validity; every `pack_overrides.rule` exists in an active pack; from phase 3, a warning for every record gate id that `gates.yaml` does not carry, and an error when two records claim one gate id with different texts without an open question naming both. Consolidation never edits a record; a collision is reported, not fixed.

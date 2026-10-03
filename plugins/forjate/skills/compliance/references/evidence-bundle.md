# Evidence per stage, the DPIA scope and sign-offs

## What exists per stage

`audit_evidence` lists kinds; `evidence_bundle` lists `<evidence>: <where>`. Only what exists at that stage, so an auditor is never pointed at a file that is not there.

| Stage | Evidence that exists | Where |
|-------|----------------------|-------|
| Crawl | the brief, the stage plan, every decision record, the verify Job's output on the seeded set, the seed strategy (synthetic or anonymised) | `.builder/`, the Job logs the runner prints |
| Walk | everything above plus `gates.yaml` with the automated checks' results, app logs with the data class per prompt and tool call, IdP access logs, the secret-scan and `.env.example` check results, the licence inventory | `.builder/gates.yaml`, the log backend the devops record names, the IdP, CI |
| Run | everything above plus the CDC stream of the decision tables the security record asked for (immutable audit trail), the restore-test report, the rotation rehearsal, the signed DPA, the approved DPIA, the subject-rights procedure | the broker's retained stream or its archive bucket, `.builder/`, the organisation's document store |

A gate "audit evidence exists" without this list is not a gate. `G-COMP-<n>` gates: `ci` for the licence inventory matching the chosen components and for the presence of the data-class field in logs; `manual` for the DPIA approval, the DPA signature and the stage sign-off, each naming the signer.

## DPIA scope

When `dpia_required: true`, the record states what the DPIA must cover so the organisation can draft it:

1. Purpose and the as-is process it replaces (from the business record).
2. Data classes, sources and volumes (from the brief and the pipeline record).
3. The model's role: what it reads, what it decides, what it can change, which inputs are untrusted (from the AI-engineering and security records).
4. The human in the loop: which decisions a person approves and how they see the context.
5. Retention per kind, the legal copy, and the erasure path.
6. Residency and every hop, with the transfer mechanism.
7. Risks to the subjects (wrong decisions on their data, exposure through logs, exfiltration through tools) and the controls from the security record.

`dpia_status: draft` when the records answer all seven; `pending` otherwise, with open questions for the missing items. Never `approved`.

## Sign-offs

| Gate | Who signs | Stage |
|------|-----------|-------|
| retention figures confirmed | finance / legal | before Run |
| DPIA approved | DPO | before Walk on `health`, before Run otherwise |
| DPA with the model provider signed | legal / procurement | before the first real datum reaches the provider |
| licence flags resolved | legal | before Run |
| subject-rights procedure defined | DPO | before Walk on `pii` at scale |
| compliance record signed for the stage | compliance officer | each transition |

Each is a `manual` gate whose text names the signer; `check.ref` points at the document (`decisions/compliance.yaml`, the DPIA, the DPA).

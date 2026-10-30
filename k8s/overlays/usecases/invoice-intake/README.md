# Use case: `invoice-intake`

> Supplier invoices arrive as PDF attachments in a shared mailbox. Someone reads each one, types supplier, amount, date and PO number into the ERP, and flags mismatches against the purchase order. We want this automated with a human approving anything that does not match.

Assembled by `forjate:kustomize` from `.builder/` (brief, stage plan, 10 decision records, gates). Success metric: invoices posted to the ERP without manual typing (baseline 0%, target 80% straight-through, 0 wrong amounts).

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up invoice-intake        # builds app/ into invoice-intake:dev, imports it, seed -> run -> verify
./scripts/ephemeral/ephemeral.sh validate invoice-intake  # re-run only the verify Job
python3 scripts/gates/gates.py run invoice-intake --transition 'crawl->walk'
kubectl kustomize --enable-helm k8s/overlays/usecases/invoice-intake/stages/walk | kubeconform -strict -ignore-missing-schemas -
```

## Decisions

| Area | Crawl | Walk | Run |
|---|---|---|---|
| ai-engineering | `apps/ai-models/ollama`. Financial data with bank account numbers and no egress allowed means local inference; extraction is a single structured call on a 7B model w | `apps/ai-models/ollama`, `apps/ai-models/litellm`. Same model behind LiteLLM for routing and cost logging; posting to Odoo is a tool that needs the clerk's approval token for anything that di | `apps/ai-models/vllm`, `apps/ai-models/litellm`. vLLM on a GPU node for throughput; the model and the eval do not change. |
| architecture | no component. A batch Job over seeded PDFs in MinIO, matched against seeded POs served by a stub of the Odoo API; nothing is exposed and nothing real is t | `apps/auth/gotrue-auth`. A scheduled worker polls the mailbox every 10 minutes, the review API serves the AP clerk's queue behind oauth2-proxy and GoTrue, approved i | `apps/auth/gotrue-auth`. Same shape, multi-entity by configuration, posting behind the approval step; durable execution revisited only if volume grows past 5k a mont |
| business | no component. Low cost PoC on seeded PDFs proves extraction and PO matching before anyone touches the real mailbox or Odoo. | no component. Real invoices with the clerk approving exceptions; the budget of 300 USD/month covers a 3-node cluster. | no component. Only worth it if Walk sustains 80%; the audit evidence requirement is what makes Run cost more than Walk. |
| compliance | no component. No regulated datum exists at Crawl | no component. Walk is where the use case acquires data subjects, an accounting record and two hops it does not control | no component. Run is the stage the evidence bundle is built for, and it is also where the retention gap stops being theoretical |
| data-pipeline | `apps/document-processing/docling`. One batch over a synthetic seed that represents the exceptions; the verify Job is the gate. | `apps/document-processing/docling`. Polling fits the volume; webhooks would need a mail provider that offers them. | `apps/document-processing/docling`. Unchanged; CDC on the decisions table is the audit stream the security expert asked for and rides on NATS if introduced. |
| data-store | `apps/databases/postgres`, `apps/minio/dev`. PDFs and parsed outputs in MinIO buckets (inbox, parsed, audit); mailbox cursor, approval status and the extraction per invoice in Postgres | `apps/databases/postgres`, `apps/minio/single-server`. Same split on Longhorn PVCs; nightly pg_dump and bucket mirror to a second node; the audit copy of invoices and decisions is retained for th | `apps/databases/postgres`, `apps/minio/single-server`. Postgres through an operator for PITR, MinIO Tenant with versioning and object lock on the audit bucket; the legal retention of the audit co |
| devops | no component. `ephemeral.sh up invoice-intake` and nothing else | `apps/continuous-delivery/argocd`, `apps/sealed-secrets`, `apps/storage/longhorn`, `apps/networking/metallb`, `apps/monitoring/prometheus`, `apps/monitoring/grafana`, `apps/monitoring/reloader`. Three k3s nodes with embedded etcd, Longhorn at 3 replicas, MetalLB for the Traefik LoadBalancer IP, and one ArgoCD Application `uc-invoice- | `apps/continuous-delivery/argocd`, `apps/security/external-secrets`, `apps/storage/longhorn`, `apps/networking/metallb`, `apps/monitoring/prometheus`, `apps/monitoring/grafana`, `apps/monitoring/otel-collector`, `apps/monitoring/reloader`. Same shape hardened, not a new architecture |
| quality | no component. The stage is proved by one Job, not by readiness | no component. From Walk the Crawl proof becomes continuous: the same inv-validate Job runs as a PostSync hook against a synthetic canary, so every deploy  | no component. Nothing in the quality design changes shape at Run; it multiplies by entity and gains the audit dimension |
| security | no component. Nothing real is reachable from Crawl, so the controls that cost money are deferred and the ones that are free now and expensive to retrofit  | `apps/sealed-secrets`, `apps/auth/gotrue-auth`. Walk is where the first real credential, the first real invoice and the first write to Odoo appear together, so every control is enforced ra | `apps/security/external-secrets`, `apps/auth/gotrue-auth`. Run keeps the Walk shape and changes where the truth about a secret lives |
| ux | no component. No packs constrain the surface, so the factory defaults apply | `apps/surveys/formbricks`. At Walk a human approves exceptions and nothing else, so the surface is the review queue the architecture record already names as the review | `apps/surveys/formbricks`. The surface does not change shape at Run; it is filtered by legal entity and the clerk's GoTrue groups decide which entities a clerk sees, w |

## Open questions

- **ai-engineering Q1** (blocks walk): Is a GPU node in the Walk budget? Without it extraction on CPU takes about 40 s per invoice, fine for 300 a month but not for a clerk waiting on screen.
- **business Q1** (blocks walk): What does a wrong amount cost today (rework, late payment fees)? Needed to price the 0-wrong-amounts target.
- **compliance Q1** (blocks run): Which jurisdiction's accounting law applies and what is the statutory retention for invoice documents and for the posting decision per invoice? The EU range is commonly 5 to 10 years and finance and legal own the figure. decisions/data-store.yaml currently sets retention_episodic 1y at Run with no retention_artifacts, and 90d for both at Walk; until the figure exists the two records disagree and retention_reconciled stays false.
- **compliance Q2** (blocks walk, pack:regulated-corp#RES-1): In which region are the shared IMAP mailbox and the Odoo instance hosted, and for any hop outside the EU, is it covered by an adequacy decision or by signed SCCs? Residency is required as eu but transfer_mechanism is unknown until both are documented.
- **compliance Q3** (blocks walk): What does the subject-rights path look like for supplier contact data: how is a person found across the Postgres rows and the MinIO objects, what does erasure do to the operational copy (delete or pseudonymise), and on what basis is the immutable audit copy retained? The DPO defines it; subject_rights_path stays open until that paragraph exists.
- **compliance Q4** (blocks walk): What are the licence terms of the ollama/qwen2.5:7b model weights chosen in decisions/ai-engineering.yaml, and do they permit this commercial production use? The catalog records the licence of the serving stack (Ollama MIT, vLLM Apache-2.0), not of the weights. Legal reads the model card; the options are accept, replace with another approved family under pack:regulated-corp#AI-1, or buy a licence. The model is the AI-engineering expert's choice, not this record's.
- **data-store Q1** (blocks run): What is the legal retention for invoice documents and the posting decisions in this jurisdiction? Needed for retention_artifacts at Run.
- **devops Q1** (blocks walk): Is a GPU node inside the Walk envelope of 120 USD/month? It costs 150 to 300 USD/month more, which the envelope does not hold. Without it CPU extraction runs at about 40 s per invoice, acceptable as a batch for 300 invoices a month but not for a clerk watching the queue. Finance ops and the CFO decide whether to raise the envelope or accept batch latency.
- **devops Q2** (blocks run, pack:regulated-corp#RES-1): Which offsite object store inside the EU receives the Run backups and the Postgres WAL archive, and who operates the restore? Velero is not a catalog component (issue #6 in docs/lab-to-production.md), so both the target and the tooling are open; the target must stay inside the EU.
- **devops Q3** (blocks run): The Run envelope is 300 USD/month and the shape this record needs costs 260 without a GPU and 410 to 560 with the GPU node vLLM requires. Business owns go_no_go: either the envelope rises, or Run accepts CPU inference on the same 3 nodes and no managed Postgres. This record keeps 300 and does not resolve it.
- **devops Q4** (blocks run, pack:regulated-corp#SEC-2): Which backing store does External Secrets read at Run, and is its region inside the EU? Most managed secret stores default to a region outside the EU, and Vault is BUSL-licensed, which the compliance record has to clear before it can be the answer.
- **quality Q2** (blocks walk): The Walk golden set is 100 anonymised real invoices carrying supplier bank account numbers. The compliance record does not exist yet: who approves reusing invoices as an evaluation corpus, what anonymisation is required, and how long may the corpus be kept?
- **security Q1** (blocks walk, pack:regulated-corp#SEC-1): pack:regulated-corp#SEC-1 requires PSA restricted from Walk, but the catalog proves none of the use case's components under it, and the mvp tier shares the cluster with other tenants. Either the platform owner accepts uc-invoice-intake-baseline at baseline and the shared namespaces in psa_exceptions, or the use case waits for restricted-capable components. The platform owner decides and records the exception; security does not accept it on their behalf.
- **security Q2** (blocks run): Does the organisation sign container images? Cosign is not in the catalog, so image_policy signed at Run is either a CI step the platform team owns or an accepted gap, decided by the platform owner before the Run tag.
- **security Q3** (blocks walk): Can the shared mailbox provider issue a per-application IMAP credential that can be rotated without affecting the humans who also read that mailbox? If not, rotation of imap-mailbox is a manual coordination with finance ops and G-SEC-9 cannot be fully automated. Finance ops and IT decide.
- **ux Q1** (blocks walk): Should approvals happen inside Odoo's own UI (a draft payable the clerk validates there) instead of the separate review queue? It saves the clerks a second tool but moves the approval token outside the use case's control and loses the PO side-by-side view. Finance ops decides before the Walk walkthrough.

## Gates

| Transition | Approver | Gates | ci | verify-job | metric | manual |
|---|---|---|---|---|---|---|
| crawl->walk | CFO | 21 | 11 | 4 | 2 | 4 |
| walk->run | CFO | 22 | 8 | 1 | 3 | 10 |

`scripts/gates/gates.py run invoice-intake --transition <t>` executes them; `manual` gates list their signer and never block.

## Checklist (kustomize skill, CONVENTION.md tiers)

- [x] builds with `kustomize build --enable-helm` and passes kubeconform (CI: validate-kustomize)
- [x] `usecase.yaml` validates; seed and verify Jobs exist suspended (CI: validate-usecases)
- [x] `.env.example` with the generate and seal header for every secret; real `.env` gitignored
- [x] plaintext-credential scan clean over the whole use case (`secret-scan.py`, CI: validate-kustomize)
- [x] from Walk: PSA labels, default-deny NetworkPolicies, the egress allow-list, sealed secrets replacing every generated Secret, the ArgoCD Application on a tag
- [ ] seal the real secrets with the recipe in each `.env.example` before the first Walk sync
- [ ] patch the hostnames (`*.example.com`) and the ArgoCD `targetRevision` to the release tag

## Assembly notes

- OPEN: the walk surface workload review-api is not in scaffold.yaml yet; the Ingress is written for the shape, the workload arrives with the walk scaffold
- OPEN: apps/minio/dev's shipped manifests meet privileged in the catalog and uc-invoice-intake-baseline enforces baseline: confirm this overlay's patches bring it to baseline, or its pods are rejected there
- OPEN: the catalog does not know the PSA level of external-secrets (apps/security/external-secrets); it is left unlabelled for its owner

# Use case: `support-copilot`

> Customers write to a Telegram group with questions about their orders and subscriptions. Two agents answer by hand, looking things up in the admin panel. We want a bot that answers the common questions itself, keeps the conversation context, and hands anything involving refunds or cancellations to a human with the full context attached.

Assembled by `forjate:kustomize` from `.builder/` (brief, stage plan, 9 decision records, gates). Success metric: share of conversations resolved without a human (baseline 0%, target 60% within 3 months, escalations carry full context).

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up support-copilot        # builds app/ into support-copilot:dev, imports it, seed -> run -> verify
./scripts/ephemeral/ephemeral.sh validate support-copilot  # re-run only the verify Job
python3 scripts/gates/gates.py run support-copilot --transition 'crawl->walk'
kubectl kustomize --enable-helm k8s/overlays/usecases/support-copilot/stages/walk | kubeconform -strict -ignore-missing-schemas -
```

## Decisions

| Area | Crawl | Walk | Run |
|---|---|---|---|
| ai-engineering | `apps/ai-models/ollama`. Local model for the replay PoC so no customer data leaves while intents are proven. | `apps/ai-models/litellm`. The brief allows egress; names, emails and phone numbers are redacted before the call and the provider sees the order id, not the customer r | out of scope |
| architecture | no component. Recorded conversations replayed against the agent API and a stub of the orders API; nothing public. | `apps/cloudflare-tunnel`. Telegram calls a webhook through the tunnel, verified by the bot's secret token; the escalation worker posts to the agents' queue with the t | out of scope |
| business | no component. Replayed conversations against a seeded orders dataset prove intent coverage and escalation quality without touching customers. | no component. Real group with two agents watching; the 150 USD/month budget covers a small cluster plus API inference. | out of scope |
| data-pipeline | no component. No context packs are active, so factory defaults apply | no component. The architecture record exposes an external surface at Walk through apps/cloudflare-tunnel with the Telegram webhook behind it, so the webho | out of scope |
| data-store | `apps/databases/postgres`. One Postgres for the PoC holds the session turns with a TTL column and the escalation records; the split into Redis happens at Walk. | `apps/databases/redis`, `apps/databases/postgres`. Redis for the live conversation, Postgres for escalations and conversation summaries by customer id; the orders API stays the system of reco | out of scope |
| devops | no component. One k3d node on a laptop or a CI runner, brought up by `ephemeral.sh up support-copilot`, which seeds the `.env` files from their examples,  | `apps/continuous-delivery/argocd`, `apps/sealed-secrets`, `apps/storage/longhorn`, `apps/monitoring/prometheus`, `apps/monitoring/grafana`, `apps/monitoring/reloader`. Three k3s nodes with embedded etcd, Longhorn at 3 replicas for the Redis and Postgres PVCs, one `uc-support-copilot` namespace under a Netwo | out of scope |
| quality | no component. The replay Job is the whole PoC, so the verify Job is where Crawl is proven: it consolidates the escalation assertion the architecture, AI-e | no component. From Walk the Crawl proof becomes continuous: the same Job runs as a PostSync hook and as a daily CronJob against one synthetic canary conve | out of scope |
| security | no component. No packs are active, so the factory defaults apply | `apps/sealed-secrets`. Walk puts the bot in front of real customers, so the overlay becomes complete in git: Sealed Secrets is the one mechanism for this stage and | out of scope |
| ux | no component. No packs are active, so the factory defaults apply | no component. The customers are already in Telegram, so the surface is the channel itself through the webhook the architecture record exposes; the support | out of scope |

## PSA exceptions

`uc-support-copilot` enforces the security record's `psa_level` per stage and is never lowered; these namespaces run below it.

| Stage | Namespace | Level | Components | Owner | Reason |
|---|---|---|---|---|---|
| walk | `longhorn-system` | privileged | `apps/storage/longhorn` | platform team | the CSI driver and the engine need privileged containers and hostPath |

## Open questions

- **ai-engineering Q1** (blocks walk): Which order fields may be shown to a customer in chat? The allowed list bounds the tools.
- **business Q1** (blocks walk): Is a wrong answer about a subscription worse than no answer? Needed to set the escalation threshold.
- **data-pipeline Q1** (blocks crawl): Which fields of the orders API may be shown to a customer in chat? The lookup and answer steps need the whitelist; until it exists the Crawl assertion on 'no field outside the whitelist' has nothing to check against. The plan carries this as an open item and it blocks the seeded fixture's shape.
- **data-pipeline Q2** (blocks crawl): Who approves the pseudonymised transcript set as the Crawl seed (security runs at this stage; compliance is skipped)? If it is not approved, the seed strategy falls back to synthetic conversations and the intent-coverage assertion weakens.
- **devops Q1** (blocks walk): `data_residency` is left unset: the brief names no region, the compliance expert is skipped in the stage plan, and the data-store record sets none — yet at Walk the conversation text leaves the cluster to an external model provider through LiteLLM and Prometheus holds conversation metrics for 90 days. Who fixes the region for the stores, the provider hop and the metrics backend, and does that reopen the compliance expert the plan skipped?
- **devops Q2** (blocks walk): The 100 USD/month Walk envelope buys three nodes plus external inference (~85) and no offsite dump target (30 to 60 more). Does the head of CS accept that 90 days of escalation transcripts are backed up only on the same cluster plus a weekly manual copy, or does the budget grow toward the brief's 150 ceiling?
- **quality Q1** (blocks crawl): Which order and subscription fields may be shown to a customer in chat? Without the allowed list the no-disallowed-field assertion has nothing to compare against; the head of CS decides. Same question as the plan's OPEN item and the AI-engineering record's Q1.
- **quality Q4** (blocks walk): Who runs the weekly human sample once the two agents are handling escalations full time, and does a missed week block the Walk gate? The head of CS decides.
- **security Q1** (blocks nothing): How is a Telegram sender bound to a customer id? Without that mapping any group member can ask about any order id they guess, and the bot cannot authorise a question (R7). If no mapping exists, the allowed answer set at Walk has to shrink to non-account questions.
- **security Q2** (blocks walk): Will the support agents get a human-facing escalation or review UI at Walk? The architecture record says api_surface external with auth_in_front api-key and no human surface, and this record agrees. If a UI appears, the value becomes oauth2-proxy with gotrue as the identity provider and the head of CS decides whether support agents authenticate against it or an existing org IdP.
- **security Q3** (blocks nothing): Is the Walk cluster shared with other tenants? If it is, the platform owner decides whether the catalog Redis and Postgres staying at baseline inside this namespace is acceptable (R8) or whether they move to their own namespace, and whether namespace-to-namespace NetworkPolicy isolation is required before Walk rather than at Run.
- **security Q4** (blocks walk): Which order fields may be shown to a customer in chat? Open in the AI-engineering record as Q1 and in the stage plan as out of scope at Crawl; it is also a security boundary, because the allowed-field list is what G-SEC-2 and G-SEC-8 assert against. Until the head of CS sets it, the assertions use the narrowest plausible list.
- **security Q5** (blocks nothing): Does the model provider's contract offer zero retention or an equivalent DPA term for this team? The plan does not run the compliance expert, so nobody else is checking; a refusal means data_egress drops to none and Walk runs on the local model with a lower resolution target.
- **ux Q1** (blocks walk): Do the support agents want a review UI of their own at Walk, or does the existing escalation queue suffice? The architecture and security records assume the existing queue with no human HTTP surface; a new UI needs oauth2-proxy and GoTrue and changes auth_in_front in three records. The head of CS decides.
- **ux Q2** (blocks walk): May the bot reply with order details in the group thread, or only in a private chat with the customer? Group replies expose order status to every member. The head of CS decides before the shadow week.

## Gates

| Transition | Approver | Gates | ci | verify-job | metric | manual |
|---|---|---|---|---|---|---|
| crawl->walk | head of CS | 16 | 6 | 6 | 2 | 2 |

`scripts/gates/gates.py run support-copilot --transition <t>` executes them; `manual` gates list their signer and never block.

## Checklist (kustomize skill, CONVENTION.md tiers)

- [x] builds with `kustomize build --enable-helm` and passes kubeconform (CI: validate-kustomize)
- [x] `usecase.yaml` validates; seed and verify Jobs exist suspended (CI: validate-usecases)
- [x] `.env.example` with the generate and seal header for every secret; real `.env` gitignored
- [x] plaintext-credential scan clean over the whole use case (`secret-scan.py`, CI: validate-kustomize)
- [x] from Walk: PSA labels (the use case's namespace at the stage's level, every other namespace at its own, the PSA exceptions in theirs), default-deny NetworkPolicies, the egress allow-list, sealed secrets replacing every generated Secret, the ArgoCD Application on a tag
- [ ] seal the real secrets with the recipe in each `.env.example` before the first Walk sync
- [ ] patch the hostnames (`*.example.com`) and the ArgoCD `targetRevision` to the release tag

---
title: "Joining the use-case and ephemeral lifecycles with NVKR and NVKE"
date: 2026-11-11
status: research
sources_verified: partial
verification_method: "NVIDIA side as in 01. Forjate side read from docs/ephemeral-use-cases.md, docs/use-case-builder/{overview,contracts}.md, scripts/ephemeral/lib/cluster.sh, scripts/gates/gates.py and the README and API types of the sibling crucible repo. The mapping itself is an interpretation, not something either side states."
---

# Joining the lifecycles

[01](01-nvke-and-nvkr.md) described NVIDIA's two lifecycles. Forjate already has two of its own: the **use-case lifecycle** (the builder and its stages) and the **ephemeral lifecycle** (`ephemeral.sh` and its Kubernetes form, Crucible). This page lines the four up, says what each is good at, and proposes the joins. Everything on the Forjate side is checked against the tree; every mapping is an interpretation.

## 1. The four lifecycles

```
USE CASE (builder, per stage)
  brief ─► stage-plan ─► decisions ─► gates.yaml ─► assemble overlay ─► ephemeral up ─► gates.py run
  Crawl ───────────────────────────► Walk ──────────────────────────► Run
  (seeded data, k3d)                 (real users, ArgoCD on a tag)    (SLAs, audits, multi-tenancy)

EPHEMERAL (ephemeral.sh / Crucible)
  Pending ─► Progressing[ stamp deadline ─ deps ─ seed ─ run ─ verify ] ─► Ready ─► Expired ─► reclaimed
                                   └─ a failed phase ─► Failed (environment kept until TTL)

NVKR (artifacts)
  Definition ─► Plan (Build Digest) ─► Run ─► Attempt (immutable) ─► qualification ─► Release ─► consumer verifies
                                                                      (Verification Policy)

NVKE (clusters)
  CreateClusterRequest ─► Provisioning ─► Provisioned ─► Updating / Upgrading / Recycling ─► Deleting
                              └─ ProvisioningFailed / UpdateFailed
```

## 2. One grammar

All four are the same shape with different objects: **declare, pin and plan, realize, prove, publish, operate, reclaim.**

| Verb | Use case (builder) | Ephemeral (`ephemeral.sh` / Crucible) | NVKR | NVKE |
|------|--------------------|----------------------------------------|------|------|
| **Declare** | `brief.yaml`, `stage-plan.yaml`, decision records | `usecase.yaml` / `UseCase` spec | Definition | cluster spec (`CreateClusterRequest`) |
| **Pin and plan** | wiki catalog resolves capabilities; packs constrain; `assemble.py` builds the overlay; `?ref=` tag for tenants | `kustomize build` of the overlay | catalog with exact pins, Plan with Build Digest, `run diff` | fixed versions (Kubernetes 1.36.3, OVN 2.4.2); immutable creation fields |
| **Realize** | scaffold + overlay | `up`: apply, seed, run | Run producing an Attempt | `Provisioning` |
| **Prove** | `gates.py run <name> --transition` | blocking `verify` Job; `Ready` | qualification: `check-artifacts`, smoke tests | `Provisioned` and `kubernetesReady` on every node |
| **Publish** | tenant root pinned to a factory tag; image write-back | `spec.outputs`: endpoints, secret references | Release: digest-pinned OCI references with SBOM and provenance | admin kubeconfig and API handed to the customer |
| **Operate** | Walk and Run stage overlays; ArgoCD with selfHeal | (not the point: short-lived) | catalog maintenance: preview and apply pin changes | `Updating`, `Upgrading`, `Recycling` within `recycleBudget` |
| **Reclaim** | the TTL is the Crawl rollback | TTL, `gc`, `Expired`, finalizer | attempts are immutable and kept | `Deleting` |

## 3. Each one is strong in a different half

| | Declare | Pin and plan | Realize | Prove | Publish | Operate | Reclaim |
|---|---|---|---|---|---|---|---|
| Use case + Crucible | **strong** (contract, packs, stages) | partial (catalog, tag pins; no digest identity) | **strong** | **strong** (blocking verify, gates) | partial (outputs yes; no signed or digest-pinned release) | partial (stages, GitOps) | **strong** (deadline stamped first, finalizer) |
| NVKR | strong | **strong** (pins, Plan, Build Digest, diff) | strong | **strong** (lanes, qualification) | **strong** (Release, SBOM, provenance, signing) | n/a | n/a |
| NVKE | strong | partial | strong | partial (node readiness; no workload proof) | weak (no authorization, kubeconfig not revocable) | **strong** (recycle budget, rolling replacement) | partial (no TTL concept found; failed `kubeadm reset` does not stop deletion) |

That matrix is the whole argument for treating them as complements: the empty cells on one row are the strong cells on another. Forjate lacks **evidence-grade publishing** and **bare-metal operation**; NVIDIA's pair lacks **a contract an agent can read**, **a blocking proof of the workload** and **a deadline**.

## 4. The joins

### J1. A second provider for `isolation: dedicated`

`dedicated` means "a cluster that exists only for this use case". Two facts make it a seam today:

- `scripts/ephemeral/lib/cluster.sh` creates, reuses and deletes **k3d** clusters only; there is no way to point the runner at a cluster it did not create.
- Crucible does not delete a dedicated cluster ("a controller cannot delete the cluster it runs on"): it sets `Expired` and "an out-of-cluster runner reads that status and deletes the cluster. The deadline still lives in exactly one place."

An NVKE workload cluster fills the same slot with GPUs: `nvkectl create cluster` is *ensure cluster*, `Provisioned` plus every node `kubernetesReady` is *cluster ready*, `nvkectl delete cluster` is the runner's reaction to `Expired`. The `usecase.yaml` contract does not change, because `isolation` states **semantics** (own cluster, residue-free) and the provider is a property of where the work runs. NVKR draws the same line: its Definitions "contain no cluster views" and the **Environment** object carries routes, credentials and signing identity.

This is also the answer the ephemeral ADR left open: the "namespace managed by a central platform" row is "the right answer at scale... its destination". NVKE is that destination for a GPU fleet.

### J2. Consumer-side policy over three-valued evidence

NVKR refuses to let absence pass: "a missing record is never evidence of success", an unevaluated suite is `not-evaluated`, "an unavailable stronger scope never falls back to weaker verification", and trust is chosen by the **consumer's Verification Policy**, never by the producer.

Forjate has both halves in different places:

- `gates.py` reports `pass | fail | skipped | pending | manual`, and by design "pending, skipped and manual never block" (it exits 1 only on a failed `ci` or `verify-job` gate). That is right at Crawl, where a metric has no data yet, and wrong at Run, where a skipped gate is an unproven claim.
- **Context packs** are already the consumer's rules: set by the organisation, overriding catalog defaults, not editable by the use case.

Proposal: a pack carries a **transition policy** saying which statuses are acceptable per transition (Crawl to Walk may accept `pending` and `manual`; Walk to Run accepts only `pass`, plus `manual` with a recorded signer). The evidence lanes map onto the stages as a vocabulary, not a feature: Crawl is `static-unqualified` (seeded data on k3d), Walk is `pipeline-attested` (the gates ran in CI against a real cluster), Run is `qualified` (rehearsed restore, kill switch exercised, audit trail present).

### J3. A use case gets an identity and a release

NVKR's **Build Digest** identifies "that generated graph's logical content", and "two outputs can share a Build Digest while requiring separate producer jobs, observations and evidence". Forjate already has the structure that makes this natural: Walk and Run are overlays *on* the Crawl overlay, "so the Crawl manifest proven on the ephemeral cluster never changes". What was proven is what is promoted.

What is missing is the name for it. A hash of `kustomize build` for the Crawl root is the use case's identity; the same identity proven on k3d and again on an NVKE cluster yields two sets of evidence for one digest, exactly NVKR's rule. A **use-case release** would bind: the factory ref, the overlay digest, the image digests, the gates report per transition and the evidence lane reached. That is also the natural home for the "image scanning and Cosign signing" item that [lab-to-production](../../lab-to-production.md) lists as a future issue, and for the tenant root's tag pin.

### J4. Proof has to outlive the environment

NVKR writes an **immutable Attempt** and keeps it, because "a missing record is never evidence of success". The ephemeral runner deliberately has **no state file**: namespace annotations are the single source of truth, which is why `ls` and `gc` survive a restart. Both are right, for different things. The annotation answers "what is alive and when does it expire". It cannot answer "did this exact use case pass, against which digest, last week", because teardown deletes the answer along with the environment.

Crucible's rule that "a failed phase leaves the environment running until its TTL" keeps the *failure* inspectable; nothing keeps the *pass*. The join: before reclaim, export a small record (use-case digest, provider, phase results, gate statuses, timestamps) to somewhere that is not the environment, and treat that record as the Attempt. Where it lives is an open decision in [03](03-stack-integration.md).

### J5. Nothing is repaired in place: replace within a budget

This is the idea that unifies the three scales, and it is the closest NVIDIA comes to the product's stance that "every company and every use case has a finite life, even a long one, and can be rebuilt".

| Scale | What is thrown away and rebuilt | Rebuilt from | Bounded by |
|-------|---------------------------------|--------------|------------|
| Artifact | node image, component build | NVKR exact pins | the Release's digests |
| Node | a worker marked `NeedsRecycle` | the pool's current release | `recycleBudget` (0 disables auto) |
| Environment | a use-case namespace or cluster | the overlay at a tag | `spec.ttl` |

A long-lived Run-stage environment is then not a different kind of thing from an ephemeral one: it is an environment with a long TTL kept alive by **rolling replacement inside a budget** instead of by in-place mutation. `recycleBudget` is the missing control: a TTL says when, a budget says how much at once, and "mark, then replace when the window allows" is a ready-made pattern for factory tag bumps on tenants that consume `base` by `?ref=`.

### J6. The environment is a declared fact, and capacity is a failure class

The builder already treats the environment as an input: GPU is read against it ("exclude `required` when no GPU node exists") and `gpu_required` is a catalog property. NVKE turns "a GPU node exists" from an assumption into a declared, requestable thing: an instance type in a site.

It also adds a failure mode k3d never had. "A NICo instance type without capacity shows as a cluster that stays in `Provisioning`." In Crucible terms that is `Progressing` with no error, forever. A provider that can stall on capacity needs its own `Progressing` reason and a provisioning timeout distinct from the three Job timeouts, or an agent waits on a cluster that will never come.

## 5. Vocabulary collisions to settle

| Word | In Forjate | In NVIDIA |
|------|-----------|-----------|
| **Run** | the third stage (SLAs, audits); also the optional middle Job `jobs.run` | one execution attempt of a Plan |
| **Plan** | `stage-plan.yaml`: scope and exit criteria per stage | a closed, pinned, diffable build graph |
| **Definition** | not used | the declaration of outputs; the closest Forjate object is the decision records plus `usecase.yaml` |
| **Release** | a tag of the factory (`v1.x.0`) | an immutable publication of artifacts plus evidence |
| **Recipe** | not used | NVKR's name for the product; Definitions are the thing |
| **Environment** | the cluster plus namespace a use case runs in | where and how work executes, publishes and signs |

Rule for writing about this: use NVIDIA's words only inside quotation marks or in the `NVKR`/`NVKE` rows of a table, and Forjate's words everywhere else. A new Forjate object that borrows a name (a use-case "release") must say so on first use.

## 6. Where the analogy breaks

- **NVKR builds artifacts; a use case deploys behaviour.** A Release proves that bytes are what a pipeline says they are. It says nothing about whether a workload does its job, which is what `verify` and the eval dimensions are for. Evidence lanes grade provenance, not correctness.
- **NVKE has no workload concept.** It creates clusters; nothing in the pages read deploys an application or reconciles git. Argo CD, Kustomize and the use-case overlay stay what they are.
- **No deadline on the NVIDIA side.** No TTL on a cluster was found in the pages read. Forjate's stamp-the-deadline-first rule has to be implemented around NVKE, not inherited from it.
- **Scale and trust model differ.** NVKE assumes TPM-attested bare metal and an operator selling clusters to customers. A use case on a mini-PC has neither the attestation nor the customer. Adopt the pattern at every scale; the product only where hardware of that kind exists.
- **Preview.** Several things the join needs (API authorization, kubeconfig revocation, management-plane upgrade and backup) are documented as absent today.

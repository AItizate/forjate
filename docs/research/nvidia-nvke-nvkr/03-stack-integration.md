---
title: "Including NVKE and NVKR in the stack as a complement"
date: 2026-11-11
status: research
sources_verified: partial
verification_method: "Proposal built on 01 and 02. Nothing here was prototyped: the first spike below exists to test the central assumption. Forjate facts checked against scripts/ephemeral/lib/cluster.sh, scripts/gates/gates.py and the crucible README."
---

# Including NVKE and NVKR in the stack

The question is not "should Forjate adopt NVKE" but "which seam lets it be used where a GPU fleet exists without making Forjate depend on it". Proposal, staged the way the use-case builder stages everything: Crawl, Walk, Run.

## The layers

```
  ┌───────────────────────────────────────────────────────────────────────────┐
  │ FORJATE  what runs inside a cluster                                         │
  │   base + components + use-case overlays   builder   gates   context packs   │
  │   Crucible: UseCase phases seed ► run ► verify ► Ready ► Expired            │
  ├──────────────── seam A: a kubeconfig, create and delete hooks ──────────────┤
  │ NVKE     which cluster exists, for how long, on which hardware              │
  │   management plane ► Cluster API / CAPNICo ► NICo ► bare-metal GPU nodes    │
  ├──────────────── seam B: a Release the operator chooses to trust ────────────┤
  │ NVKR     which bytes those clusters boot and run                             │
  │   pinned catalog ► Plan ► Run/Attempt ► Release (SBOM, provenance, signing) │
  └───────────────────────────────────────────────────────────────────────────┘
```

Seam A is where `isolation: dedicated` gets a second provider. Seam B is where an operator's node images and NVKE components arrive with evidence. Forjate needs seam A to use NVKE; it needs neither to use the **pattern**.

## What to include, and in which form

| Piece | Form | Why |
|-------|------|-----|
| NVKE as a cluster provider | a provider behind the ephemeral runner (`k3d` today, external kubeconfig, `nvke`), and a documented operator path | Fills `dedicated` with GPU capacity; no catalog component needed because NVKE is not something a use case deploys into its own cluster |
| NVKE in the catalog | **open**: possibly a management-side bundle under a new capability for cluster lifecycle | The catalog describes what runs in a cluster; NVKE runs beside the cluster. Decide in D1 below |
| NVKR's pattern | applied inside Forjate: overlay digest, canonical plan, use-case release, transition policy in packs | Independent of NVKE; the highest-value piece |
| NVKR as a tool | only where an operator builds node images or NVKE components | Not a Forjate concern otherwise |
| Mock-NICo | the Crawl test bed for the integration | Runs without GPUs, tears down, and is what makes the spike cheap |

## Crawl: one spike, on a Linux host

**Question**: does an existing Forjate use case reach `verify` exit 0 on a workload cluster created by NVKE?

1. On a Linux host or VM (the quickstart needs a virtual TPM, Docker, `kind` and inotify limits; not the Mac), follow the mock-NICo quickstart until `nvkectl get clusters` shows `Provisioned` and every node is `Ready`. About 10 to 15 minutes by the docs.
2. Fetch the workload cluster's admin kubeconfig and export it. Run the smallest existing use case's overlay by hand with `kustomize build | kubectl apply --server-side`, then the seed, run and verify Jobs in order, bypassing `ensure_cluster`.
3. Record every difference from k3d: default `StorageClass`, CNI (ovn-kubernetes, pinned), Traefik and cert-manager from `base` on a cluster Forjate did not create, Pod Security defaults, the Kubernetes version (1.36.3 pinned by NVKE against whatever k3d ships here, not checked), Docker versus containerd for image import (the runner imports `:dev` images into k3d).
4. Tear down with `nvkectl delete cluster`; note what residue remains.

**Exit criteria**: a table of deltas, one use case passing or failing with a named cause, the wall-clock of create and delete. **Not** in scope: GPUs, real NICo, any change to Forjate code.

A negative result is useful: it says seam A needs more than a kubeconfig.

## Walk: the seams in code

| Change | Where | Notes |
|--------|-------|-------|
| Provider seam in the runner | `scripts/ephemeral/lib/cluster.sh` | Today k3d-only. Introduce *ensure*, *kubeconfig*, *delete* and *ls* as provider functions; k3d stays the default and the only one CI uses. A provider the runner did not create is `external`: it never deletes |
| Provider choice is not in the contract | `usecase.yaml` stays as is | `isolation` is semantics. The provider belongs to an Environment (D2) |
| Capacity as a failure class | runner and Crucible reasons | A provisioning timeout distinct from the Job timeouts; `Progressing` with reason `waiting-for-capacity` |
| Deadline around a provider with no TTL | runner / Crucible | Stamp the deadline first (as today) and delete through the provider on `Expired`; never rely on NVKE for expiry |
| Overlay digest | builder or `scripts/ephemeral/` | Hash of the Crawl root's `kustomize build`; printed by `up`, recorded in the use-case release |
| Transition policy | `context-packs/`, read by `scripts/gates/gates.py` | Which gate statuses a transition accepts. Defaults keep today's behaviour |
| Export of the proof | runner, before reclaim | Digest, provider, phases, gate statuses, timestamps; destination per D4 |
| Wiki and catalog | `wiki/catalog-capabilities.yaml`, overrides | Only if D1 says NVKE is catalogued; then recompile after the commit |

Constraints from the repo's own rules: scripts and validators read component facts from the catalog and never name components, so the provider seam must not hard-code NVKE either; a provider is selected by configuration, and k3d remains the one every CI job can run.

## Run: a real site

- A GPU fleet with NICo, NVKE bootstrapped, API secured with the operator's identity provider, and a decision on what to do about the preview's missing management-plane upgrade and backup.
- Node images and NVKE components built by NVKR and verified under the operator's own Verification Policy (`authenticity` at least, `artifact-publication` for production), with the Release description feeding NVKE's controller and profile image references.
- Use-case releases carry evidence at `pipeline-attested` or better; Run-stage transitions accept only `pass` and signed `manual`.
- One use case demonstrated end to end on the real site, with an inference component exercising `gpu_required`.

## Risks

| Risk | Why | Mitigation |
|------|-----|------------|
| Preview churn | APIs, config and schemas change between releases; no GitHub releases from NVKE | Pin by tag and keep NVKE behind seam A; never import its types into Forjate |
| Single vendor | Apache-2.0 but no foundation | The seam is a kubeconfig and two hooks; Cluster API is the layer below, so another provider can sit at the same seam |
| Security of the preview | API on plain HTTP with auth off by default; no authorization; handed-over kubeconfigs cannot be revoked | Treat as a lab substrate until fixed; no customer data on it; short-lived admin kubeconfigs by construction (TTL) |
| Scale mismatch | TPM 2.0, SPIRE CA, Ubuntu only, an unresizable management cluster | Position for customers who already own GPU fleets; the edge-first lab does not need it |
| Kubernetes version skew | NVKE pins 1.36.3; base and components were validated against whatever the CI clusters run | The spike measures it; add the version to the environment facts |
| Vocabulary drift | "Run", "Plan", "Release" already mean something here ([02](02-lifecycle-mapping.md)) | Mapping table; NVIDIA's words only quoted |
| Pattern without product | Adopting NVKR's ideas while ignoring that its evidence model assumes a signing and registry infrastructure | Start with the digest and the transition policy, which need neither |

## Decisions for Sebas

1. **D1. Is NVKE a catalog entry or only a provider?** Provider only keeps the catalog honest (it lists what runs *in* a cluster); a catalog entry under a new capability makes the management side visible to the builder and the wiki. Recommendation: provider only until the spike shows what else the use case needs to know.
2. **D2. Introduce an Environment object separate from the use case?** It would carry provider, site, instance types, Kubernetes version and signing identity, the way NVKR separates Definition from Environment. Recommendation: yes once there is a second provider; before that it is ceremony.
3. **D3. Put the transition policy in context packs?** It reuses the existing consumer-rules mechanism and keeps today's gate behaviour as the default. Recommendation: yes, Walk stage.
4. **D4. Where does the proof of a pass live after teardown?** Candidates: an OCI registry (NVKR's answer, needs the `image-registry` capability), the `artifact-store` capability, or a git commit in the tenant repo. Recommendation: git for Lab and MVP (it is already the review surface), the registry when signing arrives.
5. **D5. Adopt NVKR's pattern independently of NVKE?** The overlay digest and the transition policy are small and useful with no NVIDIA dependency. Recommendation: yes, and do it first; it is the part that survives if NVKE never matures.
6. **D6. Which story does this tell?** For the buyer in the product framing (PyME user, fund or holding reader, edge-first), NVKE is a path to GPU capacity through a partner that already runs it, not something AItizate operates. Whether to say so in the pitch material is a product decision, not a technical one.

## Out of scope on purpose

- Running anything on NVIDIA hardware or on a real NICo.
- Adding NVKE to `k8s/components/` or any overlay.
- Changing `usecase.yaml`, the schema or the runner. The Walk table above is the list of changes to *consider* once the spike has an answer.
- Evaluating NICo itself beyond what NVKE's docs say about it.

---
title: NVIDIA NVKE and NVKR research
date: 2026-11-11
status: research
sources_verified: partial
verification_method: "docs.nvidia.com/nvke pages and the dsx-ai-factory/nvke and dsx-ai-factory/nvkr READMEs and docs/ read through a fetch tool that summarises each page; no repository was cloned and no code was run. Forjate and Crucible claims were checked against this tree and the sibling crucible repo."
---

# NVIDIA NVKE and NVKR: a complement to the Forjate stack

NVIDIA published two Apache-2.0 projects in the `dsx-ai-factory` GitHub organisation (announced 2026-11-06, both in **preview**):

- **NVKE** (NVIDIA Kubernetes Engine): a management plane that creates and operates isolated Kubernetes clusters on bare-metal GPU fleets.
- **NVKR** (NVIDIA Kubernetes Recipes): the build and release system that produces the node images and components NVKE deploys, from pinned inputs, with SBOMs, provenance and signatures.

This folder asks one question: **where do they complement Forjate, and how do their lifecycles join the use-case and ephemeral-environment lifecycles we already have?**

## TL;DR

1. **They sit below Forjate, not beside it.** NVKR supplies artifacts, NVKE supplies clusters, Forjate decides what runs inside a cluster. Nothing in NVKE or NVKR deploys workloads or does GitOps, and nothing in Forjate builds node images or provisions bare metal.
2. **The fit is a slot that already exists.** `isolation: dedicated` means "a cluster that exists only for this use case"; today only k3d fills it (`scripts/ephemeral/lib/cluster.sh` is k3d-only), and Crucible leaves the cluster deletion to "an out-of-cluster runner". An NVKE workload cluster is a second provider for that slot, with GPUs.
3. **The three lifecycles are strong in different halves.** NVKR is strong on pinning, evidence and release; NVKE on cluster operation and replacement; use case and Crucible on the contract, the blocking verify and the TTL. Each one lacks what another has ([02](02-lifecycle-mapping.md)).
4. **The most reusable part is NVKR's pattern, not NVKE's product.** Pinned catalog → canonical plan with a digest → immutable attempt → release with evidence → consumer-side verification policy. Forjate has the first and last pieces (wiki catalog, context packs) and none of the middle ([02](02-lifecycle-mapping.md), [03](03-stack-integration.md)).
5. **NVKE is datacenter-shaped.** TPM 2.0 on every node, a SPIRE CA, Ubuntu only, a management cluster that cannot be resized, upgraded or backed up in the preview. It fits the Walk/Run stages for a customer that owns GPUs, not the edge-first lab. Adopt the pattern everywhere, the product only where a GPU fleet exists.

## Documents

| # | Document | Question it answers |
|---|----------|---------------------|
| 01 | [What NVKE and NVKR are](01-nvke-and-nvkr.md) | Architecture, objects, lifecycles, platforms and preview limits, as documented. |
| 02 | [Lifecycle mapping](02-lifecycle-mapping.md) | How Definition / Plan / Run / Release and the cluster phases line up with the use-case builder, `ephemeral.sh`, Crucible and the stages; where each is strong and where the analogy breaks. |
| 03 | [Stack integration](03-stack-integration.md) | How to include them as a complement: layers, seams, a Crawl / Walk / Run adoption path, a first spike, risks and the decisions left to Sebas. |

## Relation to the rest of the repo

- [`docs/ephemeral-use-cases.md`](../../ephemeral-use-cases.md): the contract (`usecase.yaml`), the `up` lifecycle, `shared` vs `dedicated`.
- [`docs/use-case-builder/`](../../use-case-builder/overview.md): brief, stage plan, decisions, gates, context packs.
- [`docs/lab-to-production.md`](../../lab-to-production.md): the Lab / MVP / Production trajectory that the stages mirror.
- [`docs/research/agent-harness/`](../agent-harness/README.md): the other research line. It also names Crucible and an agent-step executor under a Temporal engine; an NVKE cluster is a substrate for those, not an alternative to them.
- [crucible](https://github.com/AItizate/crucible): the controller that turns a use case into a `UseCase` object with phases, outputs and a deadline.

## Sources read

- NVKE docs: [overview](https://docs.nvidia.com/nvke), [what is NVKE](https://docs.nvidia.com/nvke/documentation/overview/what-is-nvke.md), [plan your installation](https://docs.nvidia.com/nvke/documentation/install-nvke/plan-your-installation.md), [create a workload cluster](https://docs.nvidia.com/nvke/documentation/run-workload-clusters/create-a-workload-cluster.md), [manage node pools](https://docs.nvidia.com/nvke/documentation/run-workload-clusters/manage-node-pools.md), [supported platforms](https://docs.nvidia.com/nvke/documentation/overview/supported-platforms-and-versions.md), [preview status and limitations](https://docs.nvidia.com/nvke/documentation/overview/preview-status-and-known-limitations.md), [local quickstart with mock-NICo](https://docs.nvidia.com/nvke/documentation/get-started/quickstart-evaluate-locally-with-mock-ni-co.md).
- Repositories: [dsx-ai-factory/nvke](https://github.com/dsx-ai-factory/nvke), [dsx-ai-factory/nvkr](https://github.com/dsx-ai-factory/nvkr) (README, `docs/lifecycle.md`, `docs/user-concepts.md`), [the organisation page](https://github.com/dsx-ai-factory).
- Announcement coverage: [AI Weekly, 2026-11-06](https://aiweekly.co/alerts/nvidia-previews-nvke-a-bare-metal-gpu-kubernetes-factory).

## Flagged as unverified

- **Star counts and releases disagree between sources.** A search snippet gave 351 stars, 8 releases and v0.23.1 (2026-11-03) for NVKE; the organisation page showed 1,103 stars; the installation page says "NVKE does not publish GitHub releases" and tells operators to build from release tags. Treat all as unconfirmed until the repository is cloned.
- **Governance.** Every page read points to NVIDIA as the only maintainer. No foundation membership (CNCF or other) was found; absence in the pages read is not proof of absence.
- **API and CRD details.** Resource kinds beyond `Cluster`/node pool, the REST schema (`CreateClusterRequest`) and NVKR's Definition schema were not read, only described by the docs' prose.
- **Behaviour.** Nothing was run. The mock-NICo quickstart in particular is described, not executed; whether a Forjate use case verifies on an NVKE workload cluster is the first spike in [03](03-stack-integration.md).

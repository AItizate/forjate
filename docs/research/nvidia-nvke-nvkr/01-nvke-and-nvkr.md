---
title: "NVKE and NVKR: what they are, as documented"
date: 2026-11-11
status: research
sources_verified: partial
verification_method: "Vendor documentation and READMEs read through a summarising fetch tool; see the README of this folder for the page list. Quoted phrases are the docs' own words as returned by the tool."
---

# NVKE and NVKR: what they are

Facts first, no Forjate reading yet; the join is in [02](02-lifecycle-mapping.md). Everything is **preview**: both projects say commands, schemas and behaviour can change between releases and that production use is not recommended.

## At a glance

| | NVKE | NVKR |
|---|---|---|
| Expands to | NVIDIA Kubernetes Engine | NVIDIA Kubernetes Recipes |
| One line | "A management plane for GPU Kubernetes on bare metal" | "Build system and published Definitions for NVKE node OS images, packages and components" |
| Repo | `dsx-ai-factory/nvke` | `dsx-ai-factory/nvkr` |
| Language, licence | Go, Apache-2.0 | Go, Apache-2.0 |
| Who runs it | An "AI factory" operator that sells Kubernetes to its own customers | The same operator, to build what NVKE installs |
| Owns | Cluster lifecycle: create, scale, upgrade, replace, delete | Artifact lifecycle: define, plan, build, release, verify |
| Does not own | Hardware (NICo), node images (NVKR), workloads | Deployment topology and placement ("Definitions and Releases contain no cluster views") |

The operator-facing statement from NVIDIA: NVKE "is not a Kubernetes distribution and not a Cluster API flavour". It composes upstream Kubernetes (CNCF conformant), Cluster API, SPIFFE/SPIRE, OVN-Kubernetes and OpenTelemetry.

## NVKE

### Architecture

Two tiers.

- **Management cluster**: runs the NVKE management plane, Cluster API, CAPNICo (the Cluster API provider for NICo), SPIRE and the telemetry pipeline. Bootstrapped once with `nvkectl bootstrap site`.
- **Workload clusters**: the customer-facing ones. Each has its **own control plane, its own etcd** (encrypted per cluster) and one or more node pools. Nodes run `nvke-agent`.

Hardware comes from **NICo** (NVIDIA Infra Controller, `dsx-ai-factory/infra-controller`, Rust, Apache-2.0: "hardware lifecycle management and multitenant networking"). NVKE asks NICo for bare-metal machines through Cluster API; NICo boots them from an operator-hosted node image. NICo is the only provider supported by default; LaunchLayer is supported when enabled.

### Installation order

The install page lists seven sequential steps (the overview groups them as Day 0, 1 and 2):

1. Build the reference node OS image and host the boot files.
2. Prepare the management nodes: boot from the image with cloud-init, record the TPM thumbprints.
3. `nvkectl bootstrap site` forms the management cluster.
4. Install Cluster API, CAPNICo, SPIRE, telemetry and the NVKE controllers.
5. Configure NICo: verify CAPNICo, collect site, org and VPC identifiers.
6. Secure the API with tokens from the operator's identity provider.
7. Create workload clusters for customers.

What is **fixed at bootstrap** and cannot change later: node count (an odd number: 1, 3 or 5), etcd encryption, the API VIP, CPU architecture and the SPIFFE trust domain. "The management cluster cannot add or replace nodes, so size it for the life of the installation."

NVKE does not publish GitHub releases: operators check out a release tag and build `nvkectl` and the node image. Controller and profile images come from the stack config, or from an optional **NVKR release description**.

### Workload cluster lifecycle

Created with `nvkectl create cluster -f <spec>` or `POST /api/clusters`. Immutable at creation: NICo org, site and VPC, network CIDRs, `cniPlugin`. Required: name, Kubernetes version, `etcdEncrypted`, control-plane `desiredCount`, releases.

| Phase | Meaning, in the docs' words |
|-------|-----------------------------|
| `Provisioning` | "NVKE is requesting machines from NICo and forming the cluster" |
| `Provisioned` | "The first control-plane node ran `kubeadm init` and the CNI plugin is installed" |
| `Updating` / `Upgrading` / `Recycling` | Day-2 operations in progress |
| `Deleting` | Teardown: node pools, etcd encryption keys, Cluster API objects and records are removed |
| `ProvisioningFailed` / `UpdateFailed` | Error states |

Readiness is per node: the `kubernetesReady` condition on `/api/nodes` must be `True` for every node. "A NICo instance type without capacity shows as a cluster that stays in `Provisioning`": a capacity shortage looks like slowness, not like failure. On deletion NVKE attempts `kubeadm reset` on each node before releasing the NICo instance, and "a failed reset does not stop the deletion".

### Node pool lifecycle

- A pool is a group of workers sharing instance type, release and Kubernetes version, with a `desiredNodeCount` NVKE reconciles. Raising it provisions nodes; **lowering it never removes running nodes**, only pending ones.
- Changing a pool's configuration does **not** replace running nodes. **Auto mode** marks outdated nodes with the condition `nvke.nvidia.com/NeedsRecycle` and replaces at most `recycleBudget` minus the pool's shortfall at once. `recycleBudget: 0` (the default) disables it, and an operator deletes marked nodes in a maintenance window.
- Deleting a node cordons it and evicts workloads respecting PodDisruptionBudgets; if the pool falls under `desiredNodeCount`, a replacement is provisioned. Node states include `MarkedForRecycling` and `Ready`.
- Labels and taints are fixed at pool creation.

### Security and observability

- **Node identity**: SPIFFE/SPIRE with TPM attestation before a node may join. The management cluster needs the operator's own SPIRE CA.
- **Artifacts**: signed and verified, with provenance (the NVKR link).
- **Telemetry**: OpenTelemetry Collectors gather each cluster's metrics, logs and traces. The default backend is "for evaluation only": in-memory, anonymous users get Grafana admin.

### Platforms and versions

Ubuntu 26.04 or 24.04 only; Kubernetes 1.36.3 pinned for control planes, nodes and the management cluster; amd64 and arm64; ovn-kubernetes 2.4.2; CAPNICo v0.1.0; Cluster API core v1.13.6. Not supported: other OSes or Kubernetes versions, Docker (only rootful nerdctl with containerd), IPv6, other CNIs on the node image.

### Preview limitations that matter to an integrator

| Area | Limitation |
|------|-----------|
| Management cluster | Does not manage itself; no upgrade procedure for the management plane; **no backup or restore** |
| API | Plain HTTP on port 30080 with authentication off after install; **no authorization** (any authenticated caller can call every endpoint) |
| Credentials | Customers get only an admin kubeconfig; a handed-over kubeconfig cannot be revoked until its certificates expire |
| Node pools | Config changes do not replace nodes; labels and taints immutable; `nvkectl` upgrades only the control plane |
| Images | Local builds are unqualified; full-disk-encryption node images "do not protect data at rest" |
| Telemetry | Default backend is evaluation-only |

### Local evaluation

A quickstart runs **without GPUs**: a `kind` cluster (`controller-capi`) as management cluster with Cluster API, the NVKE management plane (port 8080), CAPNICo and **mock-NICo** (`nico-sim`), which answers the NICo API and starts workload nodes as **Docker containers**. Needs a Linux host or VM (6+ CPUs, 12 GiB RAM, 100 GiB disk, a virtual TPM, Docker, Go 1.27.3). About 10 to 15 minutes; `nvkectl create cluster -f cli/examples/nico-mock-cluster.yaml`, then watch `nvkectl get clusters` until `Provisioned`. It validates nothing about GPUs, real NICo or real hardware.

## NVKR

### Objects

NVKR is a pipeline with six public objects:

| Object | Question it answers |
|--------|---------------------|
| **Definition** | Which named outputs must be delivered, with which components, platforms and formats? Declarative, no cluster views |
| **Environment** | How does the work execute, where is it published, which signing settings apply? (runner routes, execution classes, publication namespace, signing identity) |
| **Run** | What happened in one attempt, and did every required output complete? |
| **Artifact** | Which exact bytes were produced or acquired? |
| **Release** | Which artifacts and evidence belong to this immutable publication? |
| **Verification Policy** | Which identities and claims will the consumer accept? |

Between Definition and Run there is a **Plan**: "a closed, pinned build graph for each output", compiled from the Definition, inspectable and diffable (`run plan`, `run graph`, `run diff`). The Plan carries a **Build Digest**, the identity of the generated graph's logical content. A Run executes against "frozen inputs and expected output slots" and leaves an immutable **Attempt** under `.nvkr/runs/<attempt>/lifecycle.json`, written transactionally so "an interrupted disk/record pair" is never read as complete.

### Inputs

- **Catalog**: reusable producer declarations with machine-managed version locks; **Source**: a named upstream repository with a release policy; **exact pins**: recorded commits, tree identities, timestamps and digests; **coordinated pin sets** derive several inputs from one upstream file.
- **Catalog overlays** replace producer instructions under the same key and are bound to the preceding digest; **toolchain substitutions** replace a build container; **Helm image bindings** map chart image slots to Definition outputs with exact digests; **catalog maintenance** previews eligible pin changes and applies them with generated files.
- **Builder types**: `oci-hermetic`, `buildkit-rootless`, `vm-image`, `nix`.

### Outputs

The NVKE CLI, container images, Helm charts, deployment bundles and **node images** (a root plus transitive materials assembled into a delivered disk; amd64 and arm64). Also bundles for **AICR** (AI Cluster Runtime). A Run can execute locally or generate GitHub Actions workflows.

### Evidence and verification

- **Evidence lanes**, weakest to strongest: `static-unqualified`, `pipeline-attested`, `qualified`.
- **Scopes** of consumer verification: `authenticity` (signed membership, signatures and provenance, signed SBOMs, no payload download), `artifact-publication` (adds payload bytes), `release` (full v1 acceptance, capability-gated). "An unavailable stronger scope never falls back to weaker verification."
- **Qualification** before a Release: `run check-artifacts` against the producing Attempt, plus smoke tests of the artifacts in network-disabled containers. "An outside-MVP suite is `not-evaluated`, never passed."
- **Invariants worth quoting**: "A missing record is never evidence of success." "An omitted or conflicting output cannot make the Run complete." "Neither the producer's Environment nor downloaded files can select consumer trust."
- Releases are published to an OCI registry as digest-pinned references tying each output to its SBOM and provenance. Errors carry stable `NVKR-E-*` codes. A Go SDK exposes Definition, Run and Release operations.
- NVKR says plainly that verification "doesn't establish byte-for-byte reproducibility or deployment readiness".

### Layout of the repository

`cmd/`, `pkg/nvkr/`, `internal/`, `inputs/` (Definitions, catalogs, configuration), `docs/` (with `adr/`, `evidence/`, `examples/`), `demos/`, `tools/`, `toolchains/`.

## Governance and licence

| | |
|---|---|
| Licence | Apache-2.0 for both (verified in the READMEs), with NOTICE and THIRD_PARTY_NOTICES in NVKR |
| Governance | Single vendor (NVIDIA), organisation `dsx-ai-factory` with a verified nvidia.com domain. No foundation found; not confirmed either way |
| Maturity | Repo created 2026-08-04 per one source; announced 2026-11-06; preview |
| Governance filter used in [the harness research](../agent-harness/00-synthesis.md) | Fails "foundation over vendor". Mitigation: the integration seam is a kubeconfig plus create/delete hooks, and the layer beneath NVKE is Cluster API (CAPNICo is a Cluster API provider), which is community-governed |

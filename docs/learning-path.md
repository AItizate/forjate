# Forjate as a learning path

The distance between a tutorial and production is where most infrastructure learning stalls.

Tutorials teach a simplified model — a `docker-compose.yml`, a single container, secrets in plaintext because "it's just local". Production is a different thing entirely: real manifests, TLS, GitOps, RBAC, secrets that never touch git. Nothing in the tutorial transfers, so the second half has to be learned on a cluster that costs money and that someone is afraid to break.

This page argues that **ephemeral use-case environments close that gap**, and that closing it is a use of Forjate worth naming on its own.

## Who this is for

The **specialized developer**: a backend, data, or ML engineer who needs infrastructure literacy but is not going to become a full-time SRE. Someone who can write the service but freezes at "now deploy it properly" — who knows their runtime cold and treats the cluster as somebody else's problem, right up until it becomes theirs.

The bet is that this person learns infrastructure best by *running real infrastructure they are allowed to destroy*, not by reading about it.

## Why the usual options fail

| Approach | What it teaches | Where it breaks |
|----------|-----------------|-----------------|
| `docker-compose` tutorial | container basics | none of it survives contact with Kubernetes — no manifests, no RBAC, no ingress, no GitOps |
| Managed cluster on a cloud trial | real Kubernetes | costs money, expires, and the fear of breaking something shared suppresses the experimentation that does the teaching |
| Reading the docs | vocabulary | you can describe a StatefulSet without ever having watched one fail to schedule |
| A company's real cluster | everything | you get read access and a ticket queue, which teaches you the org chart, not the platform |

The missing option is **something real, cheap, and yours to break**.

## What makes this different from a tutorial

An ephemeral use case is not a simplified model of production. It is **the same artifact, at a smaller scale**.

- The overlay composes `base` + catalog components the same way a paying tenant's overlay does.
- The manifests are the manifests. There is no "learning mode" that gets swapped out later.
- The security posture is the real one: restricted `securityContext`, secrets generated from files that are gitignored, no credentials in the repo.
- The same CI gates run: `kustomize build`, `kubeconform -strict`, contract linting, an end-to-end lifecycle test.

And the graduation path is already a guarantee rather than a promise. [`lab-to-production.md`](./lab-to-production.md) makes the architectural claim explicitly: *"It's additive, not destructive... You don't rewrite your overlays to go from Lab to Production."* What you learn on a laptop is not thrown away when the thing becomes real — you add NetworkPolicies, you add backups, you add GitOps gates. The composition you already understand stays put.

**That is the pedagogical property that matters: nothing learned here has to be unlearned.**

## What it actually teaches

Working through use cases exercises, in rough order of appearance:

| Concept | Where you meet it |
|---------|-------------------|
| **Composition over templating** | Kustomize base + components + overlay; no variables to hide behind |
| **Kubernetes primitives with consequences** | StatefulSets that need storage, Jobs that are immutable, Services that only resolve when a pod is ready |
| **Contract-first design** | `usecase.yaml` — declaring what an environment exposes before building it |
| **Testing infrastructure** | the seed → run → verify lifecycle; an environment that cannot prove itself is not ready |
| **Secret handling** | `secretGenerator` from gitignored `.env` files, `.env.example` committed, real values never in git |
| **Security defaults** | Pod Security Admission `restricted`, dropped capabilities, non-root, read-only root filesystem |
| **Resource discipline** | requests and limits on a machine where over-committing is immediately visible |
| **GitOps** | ArgoCD and the doctrine in [`ci-cd.md`](./ci-cd.md): *"The cluster is never written to by CI. Only ArgoCD reconciles."* |
| **Cost as a first-class constraint** | TTLs, reclamation, and the fact that an environment you forgot about is a bug |

The last one is worth dwelling on. Most infrastructure education omits **teardown** entirely — the tutorial ends when the thing starts. Here the environment expires on its own, and `gc` is a first-class command. Learning that *provisioning is the easy half* is most of what separates someone who can start a cluster from someone who can be trusted with one.

## The progression

Each step is independently useful, and none of them requires a cloud account or an API key.

**1. Prove the machinery works** — [`quickstart`](../k8s/overlays/quickstart/), about five minutes from a fresh clone. A k3d cluster, an OpenAI-compatible gateway in front of a local model, one validation Job that says yes or no.

**2. Run someone else's use case.** `ephemeral.sh up <name>`, watch the three Jobs execute in order, read the logs, connect to the endpoints the contract advertises, then tear it down.

**3. Break it on purpose.** Delete a Secret and watch the verify Job fail. Remove a resource limit and watch the node complain. This is the step that does the teaching, and it is only available because the environment is disposable.

**4. Modify one.** Add a component from the catalog to an existing use case. Discover what a `secretGenerator` wants. Discover that Jobs are immutable.

**5. Author one.** `create-usecase.sh --name <yours>`, then fill the seed, run, and verify Jobs for a problem you actually have. See [`ephemeral-use-cases.md`](./ephemeral-use-cases.md).

**6. Graduate it.** A use case that stops being disposable becomes an overlay: give it a real namespace, real secrets, a design doc and a diagram per the [overlay convention](./overlays/CONVENTION.md), and start climbing [Lab → MVP → Production](./lab-to-production.md).

## What it costs

Nothing, in the sense that matters. k3d on a laptop, Docker, and disk. No cloud account, no credit card, no API keys, no shared cluster to be careful around. The `quickstart` overlay is deliberately zero-secret so that step one cannot be blocked by credentials you do not have.

The real cost is RAM, and TTL-based reclamation exists so that cost does not accumulate quietly.

## Honest limits

A laptop cluster cannot teach everything, and pretending otherwise would undercut the point:

- **Failure at scale.** One node cannot teach you what a node failure feels like, how a rolling update behaves under real traffic, or why anti-affinity exists.
- **Cloud-specific surface.** IAM, managed load balancers, VPC networking, and provider quotas are absent by design — that absence *is* Forjate's portability argument, but it means those remain unlearned here.
- **Real load.** Performance intuition needs real traffic. Nothing here generates it.
- **Operational time.** Ephemeral environments cannot teach what only shows up after six months of uptime: certificate rotation, storage filling, dependency drift.

The honest framing: this path takes someone from *"infrastructure is somebody else's problem"* to *"I can compose, deploy, secure and verify a real stack"*. The rest needs a real cluster and real users. [`lab-to-production.md`](./lab-to-production.md) is the map for that half.

## Why this belongs in Forjate

Forjate's stated pillars are cost predictability, data sovereignty, and portability. Those are arguments aimed at people deciding *where to run things*.

This is an argument aimed at people deciding *whether they are capable of running things at all* — and it is the same artifact serving both. The overlay that teaches a developer on Monday is the overlay that runs a tenant on Friday. A factory whose smallest product is a disposable learning environment and whose largest is a multi-region tenant, built from one catalog, is a stronger claim than either half alone.

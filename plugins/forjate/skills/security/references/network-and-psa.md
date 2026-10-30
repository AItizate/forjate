# Network isolation and Pod Security per stage

| | Crawl | Walk | Run |
|---|---|---|---|
| `psa_level` | `privileged` (k3d default), labels `warn`/`audit` at `restricted` so violations show up in the PoC | `baseline` enforce, `restricted` warn and audit; `restricted` enforce when a pack says `min_psa_level: restricted` | `restricted` enforce |
| `network_policy` | `none` unless the data class is `secret` | `default-deny` ingress and egress, external destinations listed | `default-deny`, external destinations listed, per-workload matrix recommended, namespace isolation from other tenants |
| `security_context` | `restricted-compatible` on the use case's own workloads (free at Crawl, costly to retrofit) | `restricted-compatible` on every custom workload | same, enforced by PSA |
| `auth_in_front` | `none`: nothing is exposed; the runner talks to services in-cluster | `oauth2-proxy` on every human-facing surface; `api-key` on system-facing APIs | same, plus the org IdP when a pack names one |
| `image_policy` | `any` | `pinned-digest` | `signed` (Cosign in CI; not in the catalog yet, an open question if the org has no signing) |
| `audit_trail` | `none` | `app-log` with the data class per entry | `cdc` on the decision tables for regulated data, `app-log` otherwise |
| `deploy_from` | `branch` (the ephemeral runner applies from the working tree) | `tag`, ArgoCD `selfHeal: true` | `tag`, `selfHeal: true`, `prune: true` after a dry run |

The factory's reference ladder (`docs/lab-to-production.md`) puts PSA `baseline` at MVP and `restricted` at Production. Catalog databases are not all proven under `restricted`, which is why Walk enforces `baseline` and warns at `restricted` unless a pack says otherwise; the use case's own workloads are generated restricted-compatible from Crawl so the warning stays empty.

## Why these are generated, not offered

A production tenant surveyed in `docs/use-case-builder/tenant-patterns.md` had requests and limits on every one of its own Deployments and none of: PSA labels, NetworkPolicies, `securityContext`, probes. They were optional in the convention, so they were skipped under time pressure. Your record states them as settings from Walk; the kustomize skill writes the Namespace labels, the NetworkPolicies and the security contexts from those settings. A tenant that wants them off has to write a pack saying so, which is the point.

## Default-deny and the allow-list

`egress_allowlist` lists the **external** destinations the use case must reach, one hostname per line, so a reviewer sees in five lines what leaves the cluster and the kustomize skill knows what to allow besides the in-cluster traffic it derives from the architecture record's workloads and the chosen components:

```yaml
egress_allowlist:
  - odoo.corp.example.com:443        # ERP REST API, intake-worker only
  - imap.corp.example.com:993        # mailbox poll, intake-worker only
```

Rules: a destination that is "the internet" is a finding, not an entry; name the tool that needs it and bound it. DNS, the databases, MinIO, LiteLLM and the IdP are in-cluster and are not listed here: the kustomize skill writes their allows from the workloads and components, and ingress is `default-deny` plus the ingress controller's namespace to the surfaces the architecture record exposes.

Depth follows maturity. At Walk this list and `network_policy: default-deny` are the decision. A per-workload, per-port matrix (`intake-worker: postgres:5432`, ...), FQDN policies when the CNI supports them, and per-consumer policies to the inference namespace are **Run recommendations** (`egress_matrix: recommended`); the record names them in `rationale` as the next step and writes the matrix only when a pack or the reviewer asks for it (`egress_matrix: required`). A Walk record that enumerates forty port rules is harder to review than the policies it describes.

Shape the kustomize skill emits (`references/patterns.md`, "NetworkPolicy default-deny"): one `default-deny` policy selecting every pod with empty `ingress` and `egress`, one `allow-dns`, the in-cluster allows derived from the workloads, and one policy per external destination.

## Security context

The restricted-compatible set, on every container of the use case's own Deployments, StatefulSets and Jobs:

```yaml
securityContext:            # pod
  runAsNonRoot: true
  seccompProfile: { type: RuntimeDefault }
containers:
  - securityContext:        # container
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities: { drop: [ALL] }
```

`readOnlyRootFilesystem` needs an `emptyDir` for `/tmp` and any cache the runtime writes; say so in `rationale` so the scaffolder adds it. Catalog components keep their own contexts; a component that cannot run under the stage's PSA level is a PSA exception (below), not a reason to lower the level for the whole use case.

## RBAC

The use case's workloads run under their own ServiceAccount with `automountServiceAccountToken: false` unless a workload talks to the API server, in which case `rbac` from the catalog scopes a Role to the namespace. `imagePullSecrets` go on the ServiceAccount, not on every pod spec. No workload of a use case needs a ClusterRole; one that asks for it is an open question.

## Deployment posture

Observed: one ArgoCD Application on a feature branch with `automated: { prune: false, selfHeal: false }`, serving as production. Anyone with push to the branch deploys; drift stays until someone looks. Your gate from Walk, `check: {type: ci, ref: argocd-revision-check}`: the Application's `targetRevision` is a tag (or a commit), `selfHeal: true`. Prune is Run's, after a dry run (`argocd app diff`), because a wrong prune deletes state. The devops record carries `target_revision: tag` and `argocd_sync`; you demand it.

## PSA exceptions

**The rule.** The use case's namespace enforces the stage's `psa_level` and nothing lowers it. Walk enforces `baseline` with `restricted` as warn and audit, Run enforces `restricted`, a pack's `min_psa_level` can raise Walk. Whatever cannot run at that level runs in a namespace of its own, at its own level, with an owner, and the record says so in `psa_exceptions`. A reviewer reads one list to learn everything that runs below the use case's level and who accepted it.

**Why a list and not a risk.** The kustomize assembly labels each namespace and moves the components, and `validate.py` checks the list against the catalog; neither reads prose. Keep the `risks` entry for severity and mitigation and link it with `risk: R<n>`.

**Where the facts come from.** Two catalog facts per component, derived from `k8s/**` by `wiki-compile.py`: `psa_level`, the strictest Pod Security Standard its pods meet (`privileged` when they need host access, `restricted` when every container meets the profile, `baseline` otherwise, `unknown` for remote or Helm manifests the compiler cannot read), and `namespace`, set for shared infrastructure that runs in a namespace of its own. Read them for every component any record runs at the stage, not only yours: stage overlays add and never remove, so a Crawl choice still runs at Walk.

```bash
python3 -c "import json;[print(c['path'],c['psa_level'],c['namespace']) for c in json.load(open('wiki/catalog.json'))['components']]"
```

Two kinds of exception, one shape:

- **Shared infrastructure** (`namespace` set: storage, ingress, GitOps, the secrets controller, monitoring, an operator) runs in its own namespace already. Record the namespace when its components' `psa_level` is below the stage's level, so the reviewer sees a storage namespace at `privileged` and who owns it. The assembly labels it at the catalog's level.
- **A use-case-scoped component the catalog does not prove at the stage's level** (a database, the model server, the parser, the identity provider when the use case brings its own) moves out of `uc-<name>`. Put them in one namespace of the use case's own, `uc-<name>-baseline`, not in a shared one: two use cases cannot both deploy a `postgres` into the same namespace, and the components keep reaching each other by short name. The assembly moves them, leaves an alias of each Service in `uc-<name>`, seals their Secrets in the new namespace and gives it its own default-deny.

```yaml
psa_exceptions:
  - namespace: uc-<name>-baseline
    level: baseline
    components: [<the use-case-scoped paths the catalog gives psa_level baseline>]
    owner: <who sets and accepts the level>
    reason: >-
      <the catalog fact, and why the level admits them while the use case's own workloads stay at the
      stage's level in uc-<name>>
    risk: R<n>
  - { namespace: <the shared component's catalog namespace>, level: privileged, components: [<its path>], owner: <owner>, reason: "<the host access it needs>" }
```

`level` is the namespace's enforce level and must be below the stage's `psa_level`; when the components' `psa_level` is `unknown`, say so in `reason` and record the level you expect the owner to set. An `n/a` component (no pods) never needs an entry.

**Shared clusters.** On a cluster shared with other tenants the exception is the platform owner's to accept: raise an open question naming the namespaces and their levels, and leave the record's level where it is. When the only way to keep a component in `uc-<name>` would be to lower `uc-<name>`, that is the alternative you reject, with the pack rule or the ladder as the reason.

## Tenancy from Run

From Run, if the cluster is shared with other use cases or tenants: namespace per use case (already the convention), NetworkPolicy isolation between namespaces, ResourceQuota and LimitRange per namespace, PSA labels per namespace, separate ServiceAccounts, and the `multi-tenant-pattern` overlay as the reference. Say which of these the stage needs.

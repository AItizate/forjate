# Network isolation and Pod Security per stage

| | Crawl | Walk | Run |
|---|---|---|---|
| `psa_level` | `privileged` (k3d default), labels `warn`/`audit` at `restricted` so violations show up in the PoC | `baseline` enforce, `restricted` warn and audit; `restricted` enforce when a pack says `min_psa_level: restricted` | `restricted` enforce |
| `network_policy` | `none` unless the data class is `secret` | `default-deny` ingress and egress, with an allow-list | `default-deny` with an allow-list, plus namespace isolation from other tenants |
| `security_context` | `restricted-compatible` on the use case's own workloads (free at Crawl, costly to retrofit) | `restricted-compatible` on every custom workload | same, enforced by PSA |
| `auth_in_front` | `none`: nothing is exposed; the runner talks to services in-cluster | `oauth2-proxy` on every human-facing surface; `api-key` on system-facing APIs | same, plus the org IdP when a pack names one |
| `image_policy` | `any` | `pinned-digest` | `signed` (Cosign in CI; not in the catalog yet, an open question if the org has no signing) |
| `audit_trail` | `none` | `app-log` with the data class per entry | `cdc` on the decision tables for regulated data, `app-log` otherwise |
| `deploy_from` | `branch` (the ephemeral runner applies from the working tree) | `tag`, ArgoCD `selfHeal: true` | `tag`, `selfHeal: true`, `prune: true` after a dry run |

The factory's reference ladder (`docs/lab-to-production.md`) puts PSA `baseline` at MVP and `restricted` at Production. Catalog databases are not all proven under `restricted`, which is why Walk enforces `baseline` and warns at `restricted` unless a pack says otherwise; the use case's own workloads are generated restricted-compatible from Crawl so the warning stays empty.

## Why these are generated, not offered

A production tenant surveyed in `docs/use-case-builder/tenant-patterns.md` had requests and limits on every one of its own Deployments and none of: PSA labels, NetworkPolicies, `securityContext`, probes. They were optional in the convention, so they were skipped under time pressure. Your record states them as settings from Walk; the kustomize skill writes the Namespace labels, the NetworkPolicies and the security contexts from those settings. A tenant that wants them off has to write a pack saying so, which is the point.

## Default-deny and the allow-list

`egress_allowlist` is one line per workload and destination, so the kustomize skill can turn it into NetworkPolicies and a reviewer can read it:

```yaml
egress_allowlist:
  - "agent-api: postgres:5432"
  - "agent-api: minio:9000"
  - "agent-api: litellm.ai-tools:4000"
  - "worker: odoo.example.com:443"
  - "worker: imap.example.com:993"
  - "*: kube-dns:53"
```

Rules: DNS to `kube-dns` for everyone; in-cluster destinations by Service name and port; external destinations by hostname and port, which the kustomize skill maps to an IP block or a FQDN policy depending on the CNI. A destination that is "the internet" is a finding, not an allow-list entry: name the tool that needs it and bound it. Ingress is `default-deny` plus the ingress controller's namespace to the surfaces the architecture record exposes.

Shape the kustomize skill emits (`references/patterns.md`, "NetworkPolicy default-deny"): one `default-deny` policy selecting every pod with empty `ingress` and `egress`, one `allow-dns`, and one policy per allow-list line.

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

`readOnlyRootFilesystem` needs an `emptyDir` for `/tmp` and any cache the runtime writes; say so in `rationale` so the scaffolder adds it. Catalog components keep their own contexts; a component that cannot run under the stage's PSA level is a `risks` entry with the namespace it needs, not a reason to lower the level for the whole use case.

## RBAC

The use case's workloads run under their own ServiceAccount with `automountServiceAccountToken: false` unless a workload talks to the API server, in which case `rbac` from the catalog scopes a Role to the namespace. `imagePullSecrets` go on the ServiceAccount, not on every pod spec. No workload of a use case needs a ClusterRole; one that asks for it is an open question.

## Deployment posture

Observed: one ArgoCD Application on a feature branch with `automated: { prune: false, selfHeal: false }`, serving as production. Anyone with push to the branch deploys; drift stays until someone looks. Your gate from Walk, `check: {type: ci, ref: argocd-revision-check}`: the Application's `targetRevision` is a tag (or a commit), `selfHeal: true`. Prune is Run's, after a dry run (`argocd app diff`), because a wrong prune deletes state. The devops record carries `target_revision: tag` and `argocd_sync`; you demand it.

## Tenancy

From Run, if the cluster is shared with other use cases or tenants: namespace per use case (already the convention), NetworkPolicy isolation between namespaces, ResourceQuota and LimitRange per namespace, PSA labels per namespace, separate ServiceAccounts, and the `multi-tenant-pattern` overlay as the reference. Say which of these the stage needs.

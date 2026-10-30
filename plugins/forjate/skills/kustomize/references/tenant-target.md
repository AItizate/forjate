# The tenant target

A real tenant (`docs/use-case-builder/tenant-patterns.md`) has no `base/` + `overlays/` split: one root `k8s/kustomization.yaml` pulls the factory base and the cluster-level components by SSH ref pinned to one tag and composes `./namespaces/<ns>` children. A use case lands in a tenant as one namespace child, so im-u and globant consume it without translating it by hand.

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/skills/kustomize/scripts/assemble.py <usecase-dir> \
    --target tenant --tenant-repo <path-to-iac-repo> --tenant <name> --factory-ref v1.2.0 [--org AItizate]
```

## What it writes under `<repo>/k8s/`

| Output | Shape |
|--------|-------|
| `kustomization.yaml` (only when the repo has none) | `ssh://git@github.com/<org>/forjate.git//k8s/base?ref=<tag>`, the Walk infra components by SSH ref at the same tag, `./namespaces/uc-<name>`, `labels.pairs` with `app.kubernetes.io/managed-by: kustomize` and `app.kubernetes.io/overlay: <tenant>`. When the root exists, the lines to add are printed as a note instead. |
| `namespaces/uc-<name>/kustomization.yaml` | `namespace: uc-<name>`, the use-case-scoped components by SSH ref (`.git//k8s/components/...?ref=<tag>`, the double-slash form), the scaffold's workloads, `netpols.yaml`, `$patch: delete` for every factory placeholder Secret and every generated one, one `secrets/sealed-<name>.yaml` + `secrets/<name>.env.example` per secret, `images:` with the registry path and a SHA placeholder (the write-back surface `sync-app-image.yml` edits with `yq`) |
| `namespaces/uc-<name>/namespace.yaml` | PSA labels at the Walk level the security record states |
| `namespaces/<exception-ns>/` | one child per PSA exception namespace of the security record (`psa_exceptions`): the Namespace at the entry's level with owner and reason, the components it moves there by SSH ref, their sealed Secrets, default-deny; `uc-<name>` gets an ExternalName alias per moved Service (`aliases.yaml`) |
| `shared-namespaces.yaml` and Namespace label patches (only on a root it writes) | each shared namespace at the catalog `psa_level` of what runs there; on an existing root the labels are printed as notes, the tenant's owner applies them |
| `namespaces/uc-<name>/netpols.yaml` | default-deny, allow-dns, the derived in-cluster allows, one policy per external host |
| `argocd/application.yaml`, `argocd/repo-server-ssh-patch.yaml`, `argocd/cmd-params-cm-patch.yaml`, `argocd/secrets/sealed-argocd-*.yaml` + examples | the Application on a tag with `selfHeal: true`, the repo-server deploy key mount, `GIT_SSH_COMMAND`, Helm enabled, 600 s timeouts, the repo-creds template (devops `argocd_private_refs`) |
| `README.md` (or `README-<name>.md` when one exists) | the decision summary and the checklist |

Every ref is the one tag passed with `--factory-ref`; a tenant that already pins another tag moves everything to one in the same change (five factory versions side by side is the drift the survey found). Prefer `bundles/*` when several `apps/*` land in one namespace: one SSH clone per resource entry per ArgoCD refresh.

## Checking it

`kustomize build --enable-helm <repo>/k8s` resolves the SSH refs against the factory at the tag (an SSH key with read access, the same ArgoCD will need). Then `kubeconform`, `secret-scan.py` over `<repo>/k8s`, and `ref-pinning-check` semantics by eye: no `?ref=main`, no branch. The Application's `repoURL` is the tenant's own repo; patch it. The tenant's `CLAUDE.md`, if any, must describe the tree you just changed: the coordinator's review mode compares them (`tenant-drift.py`).

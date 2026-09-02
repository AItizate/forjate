---
title: component-anatomy
kind: concept
summary: what a component is made of, local vs vendored, and how nesting shows up in the wiki
summary_source: authored
links:
  - concepts/secret-strategy
---

# Anatomy of a component

A component is a directory under `k8s/components/` with a `kustomization.yaml`.
That is the entire contract. Everything else is convention, and the conventions
are worth knowing because the compiled wiki pages are shaped by them.

## Two kinds

**Local** — manifests live in this repo. `service.yaml`, `statefulset.yaml`, and
a `kustomization.yaml` listing them. [databases-postgres](../components/databases-postgres.md)
is the reference shape: a StatefulSet, a Service, and a Secret the overlay is
expected to replace.

**Vendored** — the `kustomization.yaml` holds nothing but a URL to an upstream
release manifest. [storage-longhorn](../components/storage-longhorn.md) is one
line. The factory composes someone else's release rather than restating it, and
the version discipline that requires is covered in
[remote-references](remote-references.md).

## Conventions the compiler relies on

**Placeholder hostnames.** Base and component Ingresses use
`service-name.example.com`. A hostname that looks real in a component page is a
leak of tenant configuration into a shared layer.

**The `ait-component` label.** Components tag their resources with
`app.kubernetes.io/ait-component: <name>`, which is what makes a deployed object
traceable back to the component that declared it.

**Secrets are declared, never populated.** `postgres` ships `secret.yaml`
commented out of its `resources:` precisely so the overlay must supply real
credentials. See [secret-strategy](secret-strategy.md).

**namePrefix for multiple instances.** Two postgres instances in one namespace
come from an intermediate kustomization applying `namePrefix: myapp-`, not from
copying the component.

## Nesting

Some components contain components. `appflowy` composes seven sub-directories,
each with its own `kustomization.yaml`; `gotrue-auth` composes three. The
compiler gives each a page and links it to its parent via `parent:` in
frontmatter, indented under it in the index.

The distinction that matters when reading a page: a sub-component's
`consumed_by` usually lists only its parent. That does not mean it is barely
used — it means it is reached through the parent. Only a top-level component's
`consumed_by` is a real measure of adoption.

## Adding one

1. `k8s/components/apps/{category}/{name}/` with the manifests.
2. A `kustomization.yaml` listing them, with the `ait-component` label.
3. Placeholder hostnames; no real credentials.
4. `poetry run python scripts/wiki-compile.py` — the page and its backlinks
   appear on their own. Do not hand-write the page.

`scripts/create-app-component.sh` and `scripts/create-remote-component.sh`
scaffold steps 1 and 2.

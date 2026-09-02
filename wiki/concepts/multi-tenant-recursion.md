---
title: multi-tenant-recursion
kind: concept
summary: base to org to client composition, and how the tree demonstrates it
summary_source: authored
links:
  - concepts/remote-references
  - overlays/multi-tenant-pattern-org
---

# Multi-tenant recursion

Forjate is not "shared base, separate overlays". The composition recurses: an
overlay can itself be the base of another overlay, and nothing in Kustomize
limits the depth.

```
base                      foundation every tenant inherits
 └── org overlay          what your company always needs
      └── client overlay  domain, secrets, data isolation per tenant
           └── ...        environments, regions, as deep as needed
```

## Where the tree demonstrates it

`k8s/overlays/multi-tenant-pattern/` is the worked example, and it is the only
place in the repo where an overlay references another overlay:

- [multi-tenant-pattern-org](../overlays/multi-tenant-pattern-org.md) —
  the org layer, composing base plus the components the organisation always
  wants (postgres, minio, sealed-secrets).
- [multi-tenant-pattern-tenants-client-a](../overlays/multi-tenant-pattern-tenants-client-a.md)
  and [client-b](../overlays/multi-tenant-pattern-tenants-client-b.md) — each
  holds a single local reference: the org overlay. Everything else is a
  namespace and per-client patches.

That "1 local reference" on a client page is the pattern working. A client
overlay that starts accumulating component references has stopped inheriting and
started forking, which is the failure mode to watch for in review.

## Why depth is cheap and forking is not

Each layer only records its *difference* from the layer below. A client that
patches a hostname and adds a namespace is a handful of lines; the fifty
components it inherits are not restated. The moment a client copies a component
reference rather than inheriting it, that component now has two upgrade paths,
and the org layer has quietly lost the ability to change it for everyone.

## Relation to remote tenants

The recursion works identically across repos: a remote tenant's `iac` repo is
just another layer, except its reference to the layer below is an SSH URL with a
pinned ref instead of a relative path. See
[remote-references](remote-references.md). The trade is version isolation for
propagation speed — inside one repo a change reaches every layer at once, across
repos it waits for a tag bump.

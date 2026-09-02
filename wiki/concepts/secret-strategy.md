---
title: secret-strategy
kind: concept
summary: four mechanisms coexist; which overlays use which, and what is declared but unused
summary_source: authored
links:
  - components/sealed-secrets
  - components/security-external-secrets
  - components/security-vault
---

# Secret strategy

Forjate ships four ways to get a secret into a cluster. They are not
alternatives on a roadmap — they coexist today, and different overlays picked
different ones. This page records which, because no single directory shows it.

## The four mechanisms

**`secretGenerator`** — plaintext `.env` files under the overlay's `secrets/`,
turned into Secrets at build time. The files are gitignored, so the overlay is
not self-contained: whoever deploys it must hold the `.env` out of band.
Simplest to start, worst to hand to someone else.

**[sealed-secrets](../components/sealed-secrets.md)** — Bitnami's controller.
Encrypted SealedSecrets are safe to commit, so the overlay becomes complete in
git. Decryption is bound to the controller's key, which means a cluster rebuild
without the restored key loses every secret in the repo.
`scripts/convert-to-sealed-secret.sh` handles the conversion.

**[security-external-secrets](../components/security-external-secrets.md)** —
syncs from an external store into Kubernetes Secrets.

**[security-vault](../components/security-vault.md)** — HashiCorp Vault as the
store itself.

## Who actually uses what

Derived from `resources:` references in the tree, not from intent:

| Mechanism | Overlays |
|---|---|
| sealed-secrets | [agentic-simple-workflow](../overlays/agentic-simple-workflow.md), [bare-metal-starter](../overlays/bare-metal-starter.md), [home-edge-lab](../overlays/home-edge-lab.md), [multi-cloud-portable](../overlays/multi-cloud-portable.md), [multi-tenant-pattern-org](../overlays/multi-tenant-pattern-org.md) |
| secretGenerator | [ai-dev-stack](../overlays/ai-dev-stack.md), [agentic-orchestration](../overlays/agentic-orchestration.md), [cdc-event-sourcing](../overlays/cdc-event-sourcing.md) |
| external-secrets | none |
| vault | none |

Two observations worth carrying:

**The split is by maturity, not by preference.** The overlays that represent a
deployable starting point use sealed-secrets; the ones that demonstrate a stack
use `secretGenerator`. Someone copying `ai-dev-stack` as a production template
inherits the weaker mechanism along with it.

**`external-secrets` and `vault` have no consumer in this repo.** That is not
automatically a defect — they exist so a remote tenant can activate them without
the factory shipping an opinion. But it does mean neither is exercised by
anything here: their manifests have never been built as part of an overlay in
this tree, so treat them as untested rather than as available options.

## Invariant

Generated Secret **names** appear in compiled wiki pages. Values never do. If a
value ever shows up in `wiki/`, that is a lint failure and a leak, in that order.

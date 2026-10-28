---
title: secret-strategy
kind: concept
summary: five mechanisms coexist; external-secrets syncing from openbao is the recommended store pairing; who uses what
summary_source: authored
links:
  - components/sealed-secrets
  - components/security-external-secrets
  - components/security-openbao
  - components/security-openbao-eso-store
  - components/security-vault
  - overlays/usecases-openbao-secrets
---

# Secret strategy

Forjate ships five ways to get a secret into a cluster. They are not
alternatives on a roadmap — they coexist today, and different overlays picked
different ones. This page records which, because no single directory shows it.

## The five mechanisms

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
syncs from an external store into Kubernetes Secrets. It is not a store itself.

**[security-openbao](../components/security-openbao.md)** — a store in the
cluster: OpenBao (MPL-2.0, Vault's API), configured by
`scripts/openbao/bootstrap.sh`. Besides secrets it gives people and AI agents
short-lived credentials and an SSH CA.

**[security-vault](../components/security-vault.md)** — HashiCorp Vault as the
store. **Deprecated** in favour of openbao (BUSL-1.1, file storage, no unseal
story).

## The recommended pairing

When a tenant has no store of its own, the pairing is **external-secrets
syncing from openbao**, through the
[eso-store](../components/security-openbao-eso-store.md) sub-component
(`ClusterSecretStore` `openbao`, `external-secrets.io/v1`). The two are not
alternatives: openbao is where the secret lives, external-secrets is how a
workload gets it as a Kubernetes Secret. The store's policy reads
`kv/workloads/*` only; agents' secrets under `kv/agents/<name>/` are read by the
agents themselves, never synced.

A tenant that already has a store (a cloud secret manager, an existing Vault)
keeps external-secrets and points it there instead.

## Who actually uses what

Derived from references in the tree (`resources:`, `components:` and
`transformers:`), not from intent:

| Mechanism | Overlays |
|---|---|
| sealed-secrets | [agentic-simple-workflow](../overlays/agentic-simple-workflow.md), [bare-metal-starter](../overlays/bare-metal-starter.md), [home-edge-lab](../overlays/home-edge-lab.md), [multi-cloud-portable](../overlays/multi-cloud-portable.md), [multi-tenant-pattern-org](../overlays/multi-tenant-pattern-org.md) |
| secretGenerator | [ai-dev-stack](../overlays/ai-dev-stack.md), [agentic-orchestration](../overlays/agentic-orchestration.md), [cdc-event-sourcing](../overlays/cdc-event-sourcing.md), [usecases-db-migration-a-to-b](../overlays/usecases-db-migration-a-to-b.md) |
| external-secrets + openbao | [usecases-openbao-secrets](../overlays/usecases-openbao-secrets.md) (an ephemeral test, not a tenant) |
| vault | none |

Two observations worth carrying:

**The split is by maturity, not by preference.** The overlays that represent a
deployable starting point use sealed-secrets; the ones that demonstrate a stack
use `secretGenerator`. Someone copying `ai-dev-stack` as a production template
inherits the weaker mechanism along with it.

**external-secrets and openbao are exercised, not deployed.** No tenant overlay
here uses them; they exist so a remote tenant can activate them. Unlike before,
they are no longer untested: the `openbao-secrets` use case builds and runs
both on every change to either (CI `validate-usecases.yml`), including the
store's sync and its refusals. `vault` remains unexercised.

## Invariant

Generated Secret **names** appear in compiled wiki pages. Values never do. If a
value ever shows up in `wiki/`, that is a lint failure and a leak, in that order.

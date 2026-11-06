# Secrets ladder

The mechanisms are the catalog's `secrets-mechanism` components, ranked by `secrets.rank` (`wiki/catalog.json`; `catalog-snapshot.md` shows today's ladder), with `secret-generator` as the floor every stage can use without a component (rank 0). A central store is a `secrets-store` component the top mechanism reads from, not a rung of its own. The ladder is by stage; a pack `secrets_mechanism` rule can only move a stage up it.

| Stage | `secrets_mechanism` | `choice` | What it means |
|-------|---------------------|----------|---------------|
| Crawl | `secret-generator` (the floor) | nothing | `secretGenerator` from gitignored `.env` files seeded from committed `.env.example`; the ephemeral runner and CI copy the example. Placeholder values are fine because the environment dies with its TTL. |
| Walk | the first ranked mechanism | its component | an encrypted secret committed next to the overlay, so the overlay becomes complete in git. The controller key is the single point of loss: its backup is a devops gate. |
| Run | the highest ranked mechanism, when a pack or the data class asks for a central store | its component, plus the `secrets-store` component when the organisation does not already run one | secrets pulled from a central store; rotation happens in the store, not in git. Where the catalog's `maturity` says the component has no consumer in the factory tree yet, say in `risks` that it is untested here. The store's licence is the compliance expert's to confirm. |

Higher on the ladder satisfies a lower rule (the top mechanism satisfies a rule asking for the first one); the validator ranks them through the catalog. A pack that asks for the top mechanism from Walk is satisfiable and you cite it; a pack that denies every mechanism the stage can use is an open question. When a pack denies the mechanism a stage would use, the next ranked one the stage admits is the answer.

## One mechanism per stage

A stage's `choice` carries exactly one secrets component. The move from one mechanism to the next is a gate the devops record owns ("every committed secret of the old mechanism replaced by one of the new mechanism with the same name, old files deleted, pods restarted"), not a stage in which both exist. The validator treats two mechanisms in one stage as a conflict, also inside one record.

## The `.env.example` header

Observed in a production tenant: 24 sealed secrets, 2 with an example file, rotation visible only in commit messages. Every secret the overlay consumes ships a committed `.env.example` at the same path with placeholder values and this header, so the generate and seal commands travel with the secret:

```
# <app> secrets -- replace values before sealing
# To generate: openssl rand -hex 32
# To seal:     ./scripts/convert-to-sealed-secret.sh   (select the overlay; writes secrets/sealed-<name>.yaml)
# Secret name: <name>   namespace: <ns>   keys: KEY_A, KEY_B
KEY_A=CHANGE_ME
KEY_B=CHANGE_ME
```

The kustomize skill emits the file for every `secretGenerator` entry and every `sealed-*.yaml`; your gate counts them (`check: {type: ci, ref: env-example-check}`).

## The secret scan

The same tenant committed two LLM API keys in plaintext: one as a `configMapGenerator` literal, one in an env patch, with every Secret correctly sealed. A scan limited to `secrets/` would have passed. From Walk, gate `G-SEC-<n>` with `check: {type: ci, ref: secret-scan}` covers:

- `configMapGenerator[].literals` and files under `configs/`
- `patches/*.yaml` and inline `patch:` blocks, especially `env:` entries with `value:` instead of `valueFrom`
- `*.env` files that are not gitignored, and `.env.example` files whose values are not placeholders
- Job and Deployment manifests with `env[].value` holding tokens, DSNs with passwords, or base64 blobs

Patterns a scanner catches without a vendor: `sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `-----BEGIN .* PRIVATE KEY-----`, `://[^:]+:[^@]+@` (credentials in a URL), `ghp_`, `xox[bp]-`. Name the tool when the org has one (gitleaks, trufflehog) as the `ref`; the gate stays the same.

## Replacing a factory placeholder

Catalog components ship a placeholder Secret with the name they mount (the catalog's `wiring` facts carry the names). From Walk the overlay deletes it and supplies a sealed secret of the same name; the recipe is in the kustomize skill (`references/patterns.md`, "Replacing a placeholder Secret"). Your record states the names in `rationale` so the reviewer can check each has a sealed replacement.

## Rotation

Crawl: none, the environment is disposable. Walk: a script re-seals every `.env` and the reloader restarts consumers; rehearsed once before Run (`G-SEC-<n>`, `manual`, ref `rotation-rehearsal`, the operator named; the devops record operates it, `secret_rotation: scripted`). Run: rotation in the central store, consumers pick it up through the mechanism's refresh interval; the gate is the same rehearsal.

## What goes where

| Secret | Stage it first appears | Mechanism note |
|--------|------------------------|----------------|
| database credentials | Crawl | component-mounted name; placeholder replaced at Walk |
| LLM provider API key | Crawl if egress allowed | never a literal; `data_egress: none` means there is none |
| registry pull secret | Walk | the one secret that is legitimately `cluster-wide` scoped |
| OAuth client secret, JWT signing key | Walk | lives with the IdP; rotation invalidates sessions, say so |
| webhook signing secret (Telegram, IMAP app password) | Walk | the app verifies signatures with it; an open question if the provider has none |
| sealed-secrets controller key backup | Walk | a devops gate, offsite, before any real secret is sealed |

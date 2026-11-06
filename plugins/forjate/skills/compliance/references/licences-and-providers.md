# Licences and provider terms

## Catalog components

The catalog (`wiki/catalog.json`) carries a `licence` field and a note per component, and `catalog-snapshot.md` lists every component with both on the compile date. That field is the fact; this page says what to do with it. Verify a flagged one against the upstream `LICENSE` before signing anything.

| Licence family | Examples of the family | Flag? |
|----------------|------------------------|-------|
| permissive (MIT, BSD, Apache-2.0, PostgreSQL, MPL-2.0, EPL) | most of the catalog | no; a branding clause (some BSD variants) is a note |
| weak or strong copyleft on a server you only run (GPL, LGPL) | a relational database server | no for use; flag if a client library is statically linked into a distributed product |
| network copyleft (AGPL-3.0) | an object store, a dashboard, a survey or BI tool | flag when modified or offered as a service to third parties; a note for internal use |
| source-available (SSPL, BUSL, RSAL, a sustainable-use licence) | a document database, a secrets manager, a low-code tool; a cache that changed licence between versions (check the image tag) | **flag**: not OSI-approved; corporate packs commonly deny it; production use may be allowed unless competing, legal confirms |
| model licences (community licences, custom terms) | the models an inference server serves | flag the model licence on a commercial use; the server's own licence is usually permissive |
| a service with its own terms (a tunnel, an external provider) | the client is permissive, traffic transits the vendor | note: a hop for residency, see the provider table |

`licences` lists one line per component any record chose, including the ones that pass; the auditor wants the inventory, not the exceptions. `licence_flags` lists only the flagged ones with the reason: `<component>: SSPL, denied by pack:<name>#<RULE>`.

## What a flag means

A flag is an open question for the record that chose the component, not a removal. The data-store expert chose a source-available document store for chat state; you say the licence, cite the pack if one denies it, and ask who signs. If no pack covers it, the question goes to legal with the three usual outcomes: accept for internal use, replace (name the catalog alternative the other expert listed), or buy a commercial licence.

## Model providers

| `model_provider` | `model_provider_terms` | What you need before Walk |
|------------------|------------------------|---------------------------|
| `local` (an in-cluster `inference` component) | `n/a-local` | the model's own licence in `licences`; nothing leaves |
| external API on `none`/`internal` data | `dpa-required` or the provider's standard terms | the processing region; retention of prompts; whether prompts train the model (must be no) |
| external API on `pii`/`financial`/`health` | `dpa-required` until `dpa-signed`; `zero-retention-required` when the pack or the brief says nothing may persist at the provider | a signed DPA naming the region; a zero-retention or short-retention commitment; sub-processor list; this is a transfer unless the region is inside residency |

The AI-engineering record owns the model; you own whether the terms cover the data. When they do not, the open question names the model, the provider, the data class and the rule, and blocks the stage. You never substitute a model.

## The model register

`model_register` says where the register of models in use lives. Per category (foundation, embedding, reranker, OCR, safety or judge) a line records provider, deployment option (local or external), pinned version, hosting region and data-handling terms; routing by policy (risk tier, cost, data sensitivity, jurisdiction) is the AI-engineering record's, the register is yours. `in-record` means the lines live in your `rationale` for the pilot; `org-register:<ref>` points at the organisation's. A provider retirement, policy or residency change is a reviewed configuration change at the gateway; there is no automated supply-chain feed in the factory, so say so.

## DPA checklist (what the open question should ask the organisation to confirm)

1. Processing region and sub-processors.
2. Retention of prompts, outputs and logs at the provider, and whether zero-retention is contractually available.
3. No training on customer content.
4. Breach notification window.
5. Audit rights or an equivalent certification (SOC 2, ISO 27001).
6. Deletion on termination.

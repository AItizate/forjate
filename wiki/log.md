# Wiki log

Append-only history of this wiki. Every entry starts with
`## [YYYY-MM-DD] <type> | <detail>` so it stays parseable:

```sh
grep "^## \[" wiki/log.md | tail -5
```

Types: `compile`, `concept`, `lint`, `query`.

## [2026-08-27] compile | 92 page(s) changed — 5 base, 74 component, 12 overlay
## [2026-08-27] compile | 92 page(s) changed — 5 base, 74 component, 12 overlay
## [2026-08-27] compile | 1 page(s) changed — 5 base, 74 component, 12 overlay
## [2026-08-27] compile | 22 page(s) changed — 5 base, 74 component, 12 overlay
## [2026-09-02] compile | 1 page(s) changed — 5 base, 74 component, 12 overlay
## [2026-10-28] compile | 10 page(s) changed — 5 base, 79 component, 14 overlay
## [2026-10-28] compile | 4 page(s) changed — 5 base, 79 component, 14 overlay
## [2026-10-28] concept | secret strategy: openbao as fifth mechanism, recommended pairing with external-secrets, vault deprecated
## [2026-10-28] compile | 57 page(s) changed — components:/transformers: and namespaces/ sub-kustomizations count as consumers, kinds and images only from listed files (#19)

## [2026-10-02] catalog | wiki/catalog.json added — compiled from k8s/components + catalog-overrides.yaml
## [2026-10-09] compile | 19 page(s) changed — 5 base, 74 component, 17 overlay

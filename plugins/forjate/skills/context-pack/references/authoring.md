# Authoring a context pack

## Layout

```
context-packs/<name>/
├── pack.yaml           # manifest
├── constraints.yaml    # structured rules (optional but preferred)
└── guidelines/*.md     # prose (optional)
```

## pack.yaml

```yaml
apiVersion: forjate.io/v0
kind: ContextPack
metadata:
  name: acme-platform        # lowercase, dashes; the name used in packs.yaml
  version: 1.2.0
  scope: org                 # org | team | usecase | user
  precedence: 20             # org 10-29, team 30-49, usecase 50-69, user 70-89
  description: One line.
  owner: platform-team
spec:
  applies_to: ["*"]          # or a list of roles; see roles below
  language: en
  sources:
    - id: SEC-1              # constraint ids must equal the rule id in constraints.yaml
      kind: constraint       # constraint | guideline | reference
      path: constraints.yaml#/rules/SEC-1
      enforce: must          # must | should | may
      applies_to: [security, devops]
      summary: One line a skill reads before deciding whether to open the file.
    - id: TOOLS
      kind: guideline
      path: guidelines/tool-development.md
      enforce: should
      applies_to: [ai-engineering, app-scaffold]
      summary: How agent tools are written here.
```

Roles: `coordinator`, `stage-planner`, `kustomize`, `context-pack`, `app-scaffold`, `business`, `architecture`, `ai-engineering`, `data-store`, `data-pipeline`, `security`, `compliance`, `quality`, `devops`, `ux`.

A source-level `applies_to` narrows the pack-level one. Keep sources narrow: a rule that reaches every expert is noise for most of them.

## constraints.yaml

The vocabulary is fixed so `validate.py` can check decisions against it. Each rule may carry `stages` (default: all) and `data_classes` (default: all; one of `none`, `internal`, `pii`, `financial`, `health`, `secret`) to scope when it applies.

| type | value | checked against | notes |
|------|-------|-----------------|-------|
| `deny_components` | list of component paths | `choice` | paths relative to `k8s/components/`; must exist in the catalog |
| `allow_components_only` | list of component paths | `choice` | whitelist |
| `require_components` | list of component paths | `choice` | all must be present |
| `min_psa_level` | `privileged` \| `baseline` \| `restricted` | `settings.psa_level` | |
| `secrets_mechanism` | `secret-generator` \| `sealed-secrets` \| `external-secrets` \| `vault` | `settings.secrets_mechanism` | ordered: a stronger mechanism satisfies a weaker rule |
| `model_allowlist` / `model_denylist` | list of globs (`claude-*`, `ollama/*`) | `settings.model` | |
| `data_egress` | `none` \| `anonymized` \| `any` | `settings.data_egress` | |
| `data_residency` | string (`eu`, `on-prem`) | `settings.data_residency` | exact match |
| `naming_pattern` | regex; needs `target` | `settings.<target>` | e.g. `target: namespace` |
| `max_cost_usd_month` | number | `estimated_cost_usd_month` | |
| `require_setting` | value or `"*"`; needs `target` | `settings.<target>` | presence, or exact value |
| `deny_setting_value` | value or list; needs `target` | `settings.<target>` | |

Experts expose the settings these rules look at under `spec.stages.<stage>.settings` of their Decision record. A rule that targets a setting the expert does not emit is not violated; it is simply not applicable. That is deliberate: packs constrain, they do not force every expert to talk about everything.

## guidelines/*.md

Prose for what needs judgement: how tools are written, what a security reviewer looks for, naming conventions with exceptions. Write them for the expert that will read them, in the second person, short. Put the one-line `summary` in the manifest so the expert can decide without opening the file.

## Lint

```bash
poetry run python plugins/forjate/scripts/builder/packs.py lint context-packs/<name>
```

Checks: manifest and constraints validate against their schemas; every constraint source points at an existing rule and shares its id; every guideline path exists; every component named in a rule exists in the catalog.

## Remote packs

Keep organisation packs in their own repo and pin them:

```yaml
- { name: acme-platform, source: "ssh://git@github.com/acme/platform-packs.git//security?ref=v1.2.0" }
```

Bump the ref to roll out a policy change; the use case's `packs.yaml` diff is the audit trail.

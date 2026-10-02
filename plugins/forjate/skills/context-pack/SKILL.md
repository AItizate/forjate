---
name: context-pack
description: The single interface through which every forjate skill receives external guidelines (corporate policies, security baselines, tool-development standards, a user's own rules) and through which packs are authored and activated. Use it whenever a forjate expert is about to make a decision, whenever someone mentions corporate rules, inherited constraints, compliance policies, "our standards", a pack, or asks to override a factory default for their organisation, and whenever a new pack has to be written, linted or activated for a use case.
user-invocable: true
argument-hint: "[resolve <role> | lint <pack-dir> | new <pack-name>]"
allowed-tools: Read Grep Glob Bash(poetry run python *) Bash(python3 *)
---

# Context packs

A context pack is a versioned bundle of guidelines that overrides what the Forjate catalog recommends by default. It is how "what the factory suggests" becomes "what this organisation allows". Every forjate expert consumes packs the same way, so a corporate security baseline, a tool-development standard, or a solo developer's budget rule all reach the right skill without editing any skill.

Design: `docs/use-case-builder/plan.md` §2.6. Schemas: `${CLAUDE_PLUGIN_ROOT}/scripts/builder/schemas/pack.schema.json` and `constraints.schema.json`.

## When you are an expert about to decide

Run the resolver for your own role before you reason about the use case. It merges every active pack, keeps only what applies to you, orders by precedence and inlines the structured rules:

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/packs.py resolve --for <role> --usecase-dir k8s/overlays/usecases/<name>
```

With no `.builder/packs.yaml` in the use case, the resolver returns an empty context: the factory defaults apply and you say so in your rationale.

Then apply the resolved entries like this, and no other way:

| `enforce` | Meaning for you |
|-----------|-----------------|
| `must` | A hard constraint. Never choose against it. If the use case cannot be served within it, do not quietly bend it: add an `open_questions` entry with `caused_by_rule: <ref>` and leave the stage decision explicit about what is blocked. |
| `should` | The default. Deviate only when you write the reason in `rationale`, and still cite the ref so a reviewer sees you saw it. |
| `may` | A suggestion. Mention it when relevant. |

Every ref that shaped a choice goes in that stage's `constrained_by`. This is what lets `validate.py` prove mechanically that no `must` was violated, and what lets a reviewer trace a surprising decision back to the rule that caused it.

Guideline entries come with a `summary` and a `path`. Open the file only when the summary is relevant to the decision in front of you; a 400-line security baseline does not belong in context when you are picking a message broker.

The resolver also prints `overrides`: cases where a higher-precedence pack superseded a lower one on the same rule. If an override discards a `must`, mention it in your record so `forjate:quality` can list it in `gates.yaml` under `pack_overrides`. Silent overrides are the failure mode this whole mechanism exists to prevent.

## When you are the coordinator activating packs

Ask once, during intake, which packs apply. Look in three places before asking: `context-packs/` in the repo, `~/.forjate/packs/` for the user's own, and whatever the user names. Record them in `k8s/overlays/usecases/<name>/.builder/packs.yaml`:

```yaml
apiVersion: forjate.io/v0
kind: ActivePacks
spec:
  packs:
    - { name: acme-platform, source: "ssh://git@github.com/acme/platform-packs.git//security?ref=v1.2.0" }
    - { name: my-prefs, source: ~/.forjate/packs/my-prefs }
```

Remote packs use the same URL syntax as remote components and must be pinned with `?ref=`. The resolver clones them once into `~/.cache/forjate/packs/`.

## When you are writing a pack

Read `references/authoring.md` first. The short version: a directory with `pack.yaml` (manifest: name, version, scope, precedence, sources), `constraints.yaml` (structured rules from a fixed vocabulary) and `guidelines/*.md` (prose). Structured rules are preferred whenever the rule can be expressed as one, because only those get checked by CI. Prose is for everything that needs judgement.

Lint before handing it over:

```bash
poetry run python ${CLAUDE_PLUGIN_ROOT}/scripts/builder/packs.py lint context-packs/<name>
```

Two example packs live in `context-packs/examples/`: `regulated-corp` (an org pack for a regulated company) and `solo-dev` (a user pack for a home lab). Copy the closer one.

## Precedence, in one line

Factory defaults (0) < org (10-29) < team (30-49) < use case (50-69) < user (70-89) < an explicit instruction from the user in this session. Higher wins; overrides of a `must` are logged, never hidden.

## The templated section

Every forjate skill that makes decisions carries the "Context packs" section from `references/section.md`, verbatim. When you create or edit an expert skill, paste it rather than paraphrasing it: identical wording across thirteen skills is what makes behaviour predictable and testable.

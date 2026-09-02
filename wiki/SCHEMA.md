# Wiki Schema

This file governs how the Forjate wiki is built and maintained. It is the
configuration layer of the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
the document that makes an agent a disciplined wiki maintainer instead of a
generic chatbot. Read it before touching anything under `wiki/`.

## What this wiki is

A machine-readable, compiled view of the Forjate factory, written for agents
that need to answer questions about it: what components exist, what each one
deploys, which overlays consume it, what breaks if you change it.

It is **derived from `k8s/**`**. The Kustomize tree is the source of truth.
The wiki is a compiled artifact that sits between an agent and the YAML, so the
agent does not have to re-read forty kustomizations to answer one question.

## What this wiki is not

**It is not a replacement for `docs/`.** `docs/` is human-authored prose with
judgement, narrative and voice: onboarding guides, architecture rationale,
business framing, the lab-to-production path. It is written for people.

The two trees are deliberately parallel and the boundary is one-way:

- The wiki **may link into** `docs/` (`../docs/architecture-overview.md`).
- The wiki **must never edit, restructure or duplicate** `docs/`.
- `docs/` is **not** a source for the wiki. If a fact only exists in `docs/`
  and not in `k8s/**`, it does not belong in a compiled wiki page.

The risk this boundary manages is contradiction. Two documentation trees that
both claim to describe the same component will eventually disagree, and the
reader has no way to know which one is stale. So they describe different things:
`docs/` explains *why and how to use*, the wiki records *what is actually
declared in the tree, right now*.

## The three layers

| Layer | Path | Who writes it | Mutability |
|---|---|---|---|
| Sources | `k8s/**` | Humans, via normal PRs | Mutable — this is the adaptation |
| Wiki | `wiki/**` | Agents only | Fully owned by the agent |
| Schema | `wiki/SCHEMA.md` | Co-evolved human + agent | Change deliberately |

### The adaptation that matters

In the original pattern, sources are immutable — papers and articles that never
change, so a wiki page compiled once stays true forever. **Forjate's sources
mutate.** Someone bumps a Longhorn version, adds a patch, renames a namespace.

A wiki page describing YAML that changed three weeks ago is not merely
out of date — it is *lying with the confidence of a curated page*, which is
worse than having no page at all.

Therefore every page carries `sources:` and `compiled_at:` in frontmatter, and
`scripts/wiki-lint.py` compares each source path's last commit against the
page's compile point. Drift is a lint failure, not a matter of taste.

## Directory layout

```
wiki/
├── SCHEMA.md          # this file — governs the agent
├── index.md           # content-oriented catalog; agents read this FIRST
├── log.md             # chronological, append-only, grep-parseable
├── base/              # the foundation every tenant inherits
├── components/        # one page per component under k8s/components/apps/**
├── overlays/          # one page per overlay under k8s/overlays/**
└── concepts/          # cross-cutting pages: patterns, not directories
```

`base/`, `components/` and `overlays/` mirror the tree and are **compiler-owned**.
`concepts/` has no counterpart in `k8s/` and is **agent-authored**: the recursive
multi-tenant pattern, remote SSH references, secret strategy, storage choices.
Concept pages are where synthesis lives.

## Frontmatter

Every page under `wiki/` carries YAML frontmatter. It is not decoration — the
linter and the search index both read it.

```yaml
---
title: postgres
kind: component            # component | overlay | base | concept | index
category: databases        # component/overlay grouping; omit for concepts
sources:                   # paths in k8s/** this page derives from
  - k8s/components/apps/databases/postgres
compiled_at: 2026-08-27    # date this page last reconciled with its sources
consumed_by:               # backlinks, computed — do not hand-edit
  - overlays/ai-dev-stack
links:                     # outbound wiki links, for orphan detection
  - concepts/secret-strategy
---
```

Rules:

- `sources` is **required** for `component`, `overlay` and `base` pages, and
  **must be empty or absent** for `concept` pages. A concept page that claims a
  source path is really a component page in the wrong folder.
- `consumed_by` is computed by the compiler from actual `resources:` references.
  Never write it by hand; it will be overwritten.
- `compiled_at` is only advanced when the page was genuinely reconciled against
  its sources. Advancing it to silence the linter defeats the entire mechanism.
- `summary` is the one-liner the page contributes to `index.md`. The compiler
  derives one automatically and marks it `summary_source: derived`. To write a
  better one, replace it **and** set `summary_source: authored` — only then does
  it survive recompilation. Without that flag an early machine guess would be
  frozen in place forever.

## Page conventions

Each compiled page has two clearly separated zones:

**Declared** — facts read directly out of the YAML: resources, images, ports,
labels, referenced remotes. Every statement here must be traceable to a path in
`sources`. If it is not in the tree, it does not go in this zone.

**Notes** — interpretation: what the component is for, gotchas, how it composes
with others, why an overlay patches it the way it does. This zone may draw on
`docs/`, commit history and reasoning, and **must** attribute non-obvious
claims. This is the zone where an agent is allowed to be useful rather than
merely accurate.

The hard rule: never blur the zones. An agent reading a page must be able to
tell which lines are mechanically true and which are someone's judgement.

## Operations

**Compile.** `scripts/wiki-compile.py` regenerates the Declared zone of every
compiler-owned page from `k8s/**` and recomputes `consumed_by` backlinks. It
preserves the Notes zone verbatim — prose survives recompilation. Run it after
any change to the Kustomize tree.

**Query.** An agent answering a question reads `index.md` first, then drills
into pages. Beyond the index, `qmd` provides hybrid search (see below). Per the
pattern: **good answers get filed back into the wiki** as `concepts/` pages
rather than evaporating into chat history. A question worth asking twice is a
page.

**Lint.** `scripts/wiki-lint.py` checks source drift, dangling sources, broken
links, orphan concept pages, schema violations, and components present in the
tree but missing a page. Drift, schema and dangling are hard failures; the rest
are warnings unless `--strict`. It reuses the compiler's traversal through
`scripts/wiki_compile_api.py` rather than duplicating it, so the two can never
disagree about what counts as a page. Run it in CI and before releases.

## log.md

Append-only. Every entry starts with a fixed, parseable prefix so plain unix
tools work on it:

```
## [2026-08-27] compile | 48 components, 10 overlays
## [2026-08-27] concept | multi-tenant recursion
## [2026-08-27] lint    | 3 drifted pages
```

`grep "^## \[" wiki/log.md | tail -5` gives recent history. Entry types are
`compile`, `concept`, `lint`, `query`.

## Search

The index alone is adequate at this scale — the original pattern puts the
breaking point around a hundred sources, and Forjate sits just under it.
`qmd` is installed on top for hybrid BM25 + vector + rerank search:

```sh
qmd search  "sealed secrets" -c forjate-wiki     # BM25, no model, instant
qmd vsearch "how tenants pin a version" -c forjate-wiki   # semantic
qmd query   "how tenants pin a version" -c forjate-wiki   # hybrid + rerank
```

**Pick the command to match the machine.** `qmd search` is pure BM25 and needs
no model, so it is instant everywhere. `vsearch` and `query` load GGUF models;
without GPU acceleration a single query can take minutes, which on a CPU-only
box makes them unusable for an agent mid-task. Check with `qmd doctor` — if it
reports "running on CPU", treat `qmd search` plus `wiki/index.md` as the real
retrieval path and reserve the semantic commands for offline exploration.

Collections and their context strings are registered once by
`scripts/wiki-search-setup.sh`. After that, `scripts/wiki-update.sh` is the
single command that recompiles, lints and re-indexes in one pass. Note that
`qmd embed` alone is not enough after adding a page: it only vectorises what
the index already knows about. `qmd update` is what re-scans for new files.

## Rules for the agent

1. Never invent a value. Ports, images, versions and names come from the tree.
2. Never edit `docs/`. Link to it instead.
3. Never hand-edit `consumed_by` or generated Declared zones — edit the source
   or the compiler.
4. Update `index.md` and append to `log.md` in the same pass as any wiki change.
5. When a source path disappears, do not silently delete the page. Mark it
   `kind: retired`, keep the history, and note what replaced it.

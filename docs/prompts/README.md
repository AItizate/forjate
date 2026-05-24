# Diagram prompts

Versioned prompts for every architecture diagram in this repo. Generated with the [Gemini CLI](https://geminicli.com/) + [nanobanana extension](https://github.com/gemini-cli-extensions/nanobanana).

## Why prompts are versioned

The image is the artifact. The prompt is the source. When the architecture changes — a new component, a renamed layer — the prompt is edited, re-run, and the resulting PNG replaces the previous one in `docs/assets/architecture/`.

## Setup

```bash
# Once
gemini extensions install https://github.com/gemini-cli-extensions/nanobanana
export NANOBANANA_API_KEY="..."   # from https://aistudio.google.com/apikey

# Per generation
gemini -y -p "$(cat docs/prompts/01-reference-architecture.md | sed -n '/^```bash/,/^```$/p' | sed '1d;$d')"
```

## Catalog

| # | Prompt | Output | Status |
|---|--------|--------|--------|
| 01 | [`01-reference-architecture.md`](./01-reference-architecture.md) | `assets/architecture/reference-architecture.png` | v0.4 |
| 02 | [`02-scale-spectrum.md`](./02-scale-spectrum.md) | `assets/architecture/scale-spectrum.png` | v0.2 |
| 03 | [`03-multi-tenant-pattern.md`](./03-multi-tenant-pattern.md) | `assets/architecture/multi-tenant-pattern.png` | v0.1 — also embedded in the `multi-tenant-pattern` overlay doc |
| 04 | [`04-overlay-agentic-simple-workflow.md`](./04-overlay-agentic-simple-workflow.md) | `assets/architecture/overlay-agentic-simple-workflow.png` | v0.3 |
| 05 | [`05-overlay-home-edge-lab.md`](./05-overlay-home-edge-lab.md) | `assets/architecture/overlay-home-edge-lab.png` | v0.4 |
| 06 | [`06-overlay-bare-metal-starter.md`](./06-overlay-bare-metal-starter.md) | `assets/architecture/overlay-bare-metal-starter.png` | v0.2 |
| 07 | [`07-overlay-multi-cloud-portable.md`](./07-overlay-multi-cloud-portable.md) | `assets/architecture/overlay-multi-cloud-portable.png` | v0.1 |

## Design language (applied to all prompts)

- **Background**: deep navy `#0A1428`
- **Primary accent**: light blue `#5BB4FF` (titles, borders, dividers)
- **Secondary accent**: cyan `#7AE7FF` (highlighted chips)
- **Text**: white labels, clean geometric sans-serif (Inter / Plus Jakarta vibe)
- **Style**: flat, technical, investor-deck polish
- **No**: photos, 3D, raster textures, logos, company names, watermarks
- **Aspect**: 16:9 wide, cinematic frame, 1920x1080 minimum target

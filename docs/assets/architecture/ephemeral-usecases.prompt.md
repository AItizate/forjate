# Ephemeral use-case environments

**Output:** `ephemeral-usecases.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.1
**CLI:** antigravity-cli (`agy`) v1.1.21 — `generate_image` tool
**Model:** `gemini-3.1-pro-high` (Gemini 3.1 Pro, High)

The lifecycle diagram for disposable per-use-case environments. A runner reads a contract, brings up a cluster, seeds it, proves it works, and reclaims it when the TTL expires — the question the diagram answers is _how does a use case become a running, agent-consumable environment and then disappear?_

Generated through antigravity-cli rather than the `gemini` CLI the earlier diagrams used. `agy` drives image generation through its `generate_image` tool, so the prompt is handed to the model as an instruction rather than through a `/generate` slash command. Run it from this directory; `agy models` lists the alternatives if the chosen one drifts from the house style.

## Command (v0.1)

```bash
agy --model gemini-3.1-pro-high --print-timeout 10m --dangerously-skip-permissions \
  -p 'Use the generate_image tool to create ONE 16:9 image and save it in the current directory as ephemeral-usecases.png. Use the following text verbatim as the image prompt, without summarizing or editing it: Architecture and lifecycle diagram for ephemeral use-case environments in Forjate, a Kustomize-driven Kubernetes factory. A single generic runner script reads a declarative contract file per use case, brings up a local k3d cluster, applies the overlay, runs three jobs in sequence, and reclaims the environment when its time-to-live expires. Two isolation strategies exist side by side. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL, SIDE. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

Near the left edge, a tall narrow rounded rectangle in cyan labeled AI AGENT with a small terminal icon. Inside it two chips in tiny cyan monospace: reads usecase.yaml and connects to endpoints. A thin dotted cyan arrow leaves this box toward the middle of the image.

Immediately to its right, a rounded rectangle in amber labeled ephemeral.sh with six small chips stacked in tiny monospace: up, seed, validate, down, ls, gc. Below the chips a tiny cyan monospace line: one runner, every use case.

Above the runner box, a small magenta document icon labeled usecase.yaml with three tiny monospace lines beneath it: isolation, ttl, outputs. A thin magenta arrow points down from this document into the ephemeral.sh box, annotated in tiny amber monospace: the contract.

A thick cyan arrow goes rightward from ephemeral.sh into a large rounded rectangle occupying the middle of the frame, labeled K3D CLUSTER in amber at its top edge. The arrow is annotated in tiny amber monospace: kustomize build then apply.

Inside the large cluster rectangle, a single sub-rectangle with the namespace label uc-db-migration-a-to-b in amber monospace at its top, and a small amber tag attached to its corner reading expires-at 4h in tiny monospace.

Inside that namespace sub-rectangle, three magenta job chips arranged in a clear horizontal sequence connected by short magenta arrows: a chip labeled seed (Job) with tiny cyan subtitle load fixtures, a chip labeled run (Job) with tiny cyan subtitle the actual work, a chip labeled verify (Job) with tiny cyan subtitle blocks until exit 0. Beneath the three job chips, two cyan chips side by side labeled postgres (StatefulSet) and mongodb (StatefulSet), with a thin cyan connector from each up into the seed chip.

A thin dotted cyan arrow arrives from the AI AGENT box on the far left and terminates at the postgres and mongodb chips, annotated in tiny amber monospace: svc.uc-name.svc.cluster.local

Beneath the large cluster rectangle, a horizontal band split into two adjacent rounded boxes of equal width. The first is labeled SHARED in cyan monospace with tiny cyan subtitle lines: one reusable cluster, namespace per use case, seconds to start. The second is labeled DEDICATED in magenta monospace with tiny cyan subtitle lines: one cluster per use case, required for CRDs and operators, total teardown. A thin vertical divider separates them.

Near the right edge, a rounded rectangle in amber labeled gc with a small clock icon, and beneath it two tiny monospace lines: expires-at in the past and reclaim. A thin amber dashed arrow curves from this box back leftward into the namespace sub-rectangle inside the cluster, annotated in tiny amber monospace: ephemeral means ephemeral.

Across the bottom of the image, a horizontal cyan callout band with text in cyan monospace: a use case is an overlay with a shorter life expectancy.

At the very bottom, a single horizontal amber bar in monospace reading UP. SEED. PROVE IT. THROW IT AWAY.

A tiny terminal artifact in the bottom-left corner reads > forjate:ephemeral-usecases_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom.'
```

`--dangerously-skip-permissions` is what lets the run write the file without an interactive prompt. To avoid the blanket flag, add a narrower `permissions.allow` rule for the `command` permission in antigravity's `settings.json` instead.

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Approved as generated.** Covers the contract → runner → cluster → three-job lifecycle flow, the shared/dedicated isolation split, TTL-driven gc, and the agent consuming resolved endpoints. One pass, no rework — none of the banned layout words leaked into the render. The isolation band came out inside the cluster box rather than beneath it; noted rather than regenerated, since the two strategies read clearly either way. |

# Overlay: quickstart

**Output:** `overlay-quickstart.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.1 (pending regeneration)

The fresh-clone smoke test. A laptop, k3d, Ollama, one model, one validation Job. Zero secrets, zero ingress, zero auth — the question the diagram answers is simply _is the LLM responding?_

## Command (v0.1)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the quickstart overlay of Forjate. A laptop running a local Kubernetes cluster on k3d with one purpose only: prove the factory works by running a single LLM and validating it end-to-end. No ingress, no TLS, no auth, no secrets. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL, SIDE. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

A small hardware inventory callout at the top-left corner: a single laptop icon labeled LAPTOP joined by a thin line to a small box labeled k3d (1 server + 1 agent). Subtitle in tiny cyan monospace: ~25 min from clone.

On the left side of the image, a single rounded rectangle labeled DEVELOPER in cyan. Inside: a small terminal icon and a chip labeled 01_init_cluster.sh in cyan monospace, a chip labeled 02_deploy.sh in cyan monospace, and a chip labeled 03_validate.sh in amber monospace. Below the chips, in tiny cyan monospace: three scripts. one command each.

A horizontal cyan arrow goes rightward from the DEVELOPER box into a large rounded rectangle in the middle. The arrow is annotated in tiny amber monospace with kubectl apply -k.

The large rounded rectangle in the middle reads KUBERNETES CLUSTER (k3d, 2 nodes) in amber at its top. Inside the cluster, a single sub-rectangle with the namespace label ai-tools in amber monospace at the top.

Inside the ai-tools sub-rectangle, two chips stacked vertically with a thin cyan connector between them:
- Top chip in cyan monospace: ollama (StatefulSet) with a smaller subtitle line in tiny cyan: serves gemma4:e2b-it-q4_K_M
- Bottom chip in magenta monospace: quickstart-validate (Job) with a smaller subtitle line in tiny cyan: POST /api/generate then assert response

A thin magenta arrow goes from the quickstart-validate chip up to the ollama chip with the annotation in tiny amber monospace: in-cluster smoke test.

To the right of the ollama chip, a small attached cyan box labeled PVC 10Gi in tiny monospace, with a thin connector indicating the model storage.

OUTSIDE the cluster on the right side, a small rounded rectangle labeled OPERATOR in cyan monospace with a tiny terminal icon and a chip labeled kubectl port-forward 11434 in tiny cyan monospace. A thin dotted cyan arrow goes from this OPERATOR box into the ollama chip inside the cluster, annotated in tiny amber monospace: after Job passes — talk to the model.

Across the bottom of the cluster, a horizontal cyan callout band with text in cyan monospace: no ingress. no TLS. no secrets. one Job tells you it works.

At the very bottom of the image, a single horizontal amber bar in monospace reading QUICKSTART — DOES IT WORK YES OR NO.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-quickstart_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Pending regeneration with nanobanana.** Drafted alongside the overlay code; the PNG must be produced from this prompt before merge. |

# Overlay: quickstart

**Output:** `overlay-quickstart.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.2

The fresh-clone smoke test. A laptop, k3d, LiteLLM in front of Ollama serving Gemma 3 1B, one validation Job. Zero secrets, zero ingress, zero auth — the question the diagram answers is _is the LLM responding through the production gateway shape?_

## Command (v0.2)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the quickstart overlay of Forjate. A laptop running a local Kubernetes cluster on k3d with one purpose only: prove the factory works end-to-end by deploying the same OpenAI-compatible gateway shape every production tenant uses, with a single local model behind it. No ingress, no TLS, no auth, no secrets. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL, SIDE. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

A small hardware inventory callout at the top-left corner: a single laptop icon labeled LAPTOP joined by a thin line to a small box labeled k3d (1 server + 1 agent). Subtitle in tiny cyan monospace: ~5 min from clone.

On the left side of the image, a single rounded rectangle labeled DEVELOPER in cyan. Inside: a small terminal icon and three chips stacked vertically — 01_init_cluster.sh in cyan monospace, 02_deploy.sh in cyan monospace, 03_validate.sh in amber monospace. Below the chips, in tiny cyan monospace: three scripts. one command each.

A horizontal cyan arrow goes rightward from the DEVELOPER box into a large rounded rectangle in the middle. The arrow is annotated in tiny amber monospace with kubectl apply -k.

The large rounded rectangle in the middle reads KUBERNETES CLUSTER (k3d, 2 nodes) in amber at its top. Inside the cluster, a single sub-rectangle with the namespace label ai-tools in amber monospace at the top.

Inside the ai-tools sub-rectangle, three chips arranged with clear flow:

- Magenta chip near the inner upper edge of the namespace box labeled quickstart-validate (Job) with a smaller subtitle line in tiny cyan monospace: POST /v1/chat/completions then assert response.
- Cyan chip in the middle labeled litellm (Deployment) with a smaller subtitle line in tiny cyan monospace: OpenAI-compatible gateway on :4000.
- Cyan chip near the inner lower edge labeled ollama (StatefulSet) with a smaller subtitle line in tiny cyan monospace: serves gemma3:1b (~815 MB).

A thin magenta arrow goes from the quickstart-validate chip down to the litellm chip with the annotation in tiny amber monospace: in-cluster smoke test.

A thin cyan arrow goes from the litellm chip down to the ollama chip with the annotation in tiny amber monospace: proxies to local backend.

To the right of the ollama chip, a small attached cyan box labeled PVC 10Gi in tiny monospace, with a thin connector indicating the model storage.

OUTSIDE the cluster on the right side, a small rounded rectangle labeled OPERATOR in cyan monospace with a tiny terminal icon and a chip labeled kubectl port-forward svc/litellm 4000 in tiny cyan monospace. A thin dotted cyan arrow goes from this OPERATOR box into the litellm chip inside the cluster, annotated in tiny amber monospace: after Job passes — same OpenAI API your apps already speak.

Across the bottom of the cluster, a horizontal cyan callout band with text in cyan monospace: no ingress. no TLS. no secrets. one Job tells you it works.

At the very bottom of the image, a single horizontal amber bar in monospace reading QUICKSTART — DOES IT WORK YES OR NO.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-quickstart_v0.2 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | Initial draft: Ollama-only (no LiteLLM), Gemma 4 E2B, ~25 min from clone, port-forward to 11434. Never generated. |
| **v0.2** | **Reflects current overlay.** Adds LiteLLM gateway chip between validate-Job and ollama, switches default model to gemma3:1b, updates timing to ~5 min, port-forward target moves to svc/litellm:4000. |

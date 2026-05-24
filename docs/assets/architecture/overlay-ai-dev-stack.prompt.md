# Overlay: ai-dev-stack

**Output:** `overlay-ai-dev-stack.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.1

Local AI workbench on a k3d cluster. Three namespaces with distinct roles, all behind one sign-in.

## Command

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the ai-dev-stack overlay of Forjate. A laptop-class Kubernetes cluster on k3d that hosts a local AI workbench. Three namespaces with distinct roles, one shared sign-in surface. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

A small hardware inventory callout at the top-left corner: a single icon labeled LAPTOP / WORKSTATION connected by a thin line to a small box labeled k3d (2 nodes). Subtitle in tiny cyan monospace: spin up in 15 min.

On the left side of the image, a single rounded rectangle labeled DEVELOPER in cyan. Inside: a small user icon and a chip labeled BROWSER. A horizontal arrow goes right toward the cluster, passing through a thin magenta-tinted vertical gate at the cluster edge labeled OAuth2 Proxy + GoTrue (one sign-in).

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER (k3d, 2 nodes) in amber. Inside the cluster, three side-by-side rounded sub-rectangles separated by thin vertical dotted cyan dividers. Each sub-rectangle has its namespace label in amber monospace at the top.

First sub-rectangle — heading ai-tools. Chips inside: LiteLLM (Inference Gateway), vLLM (Local LLM Serving). A small subtitle in tiny cyan monospace: one gateway, swappable backend.

Second sub-rectangle — heading dev. Chips inside: Milvus (Vector Store), etcd (Milvus metadata), MinIO (Object Storage), Node-RED (Low-code Flows). A small subtitle in tiny cyan monospace: your sandbox.

Third sub-rectangle — heading security. Chips inside: whoami (smoke test), shared sign-in services. A small subtitle in tiny cyan monospace: auth + smoke.

OUTSIDE the cluster on the right side, a rounded rectangle labeled OPEN UI in cyan with three chips stacked: Open WebUI, Node-RED Editor, MinIO Console. Three thin cyan arrows from inside the cluster (from LiteLLM, Node-RED, and MinIO respectively) flow rightward to these UI chips, all passing through the cluster ingress.

Across the bottom of the cluster, a horizontal cyan callout band with text in cyan monospace: three namespaces. one cluster. one sign-in.

At the very bottom of the image, a single horizontal amber bar in monospace reading AI-DEV-STACK — PROTOTYPE TODAY. SHIP TOMORROW.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-ai-dev-stack_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Final.** Approved on first pass. |

# Lab → MVP → Production

**Output:** `lab-to-production.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.1

Narrative diagram showing the trajectory of a Forjate deployment: from a single-node Lab, to a 3-node MVP, to a Production-graded cluster. Each stage adds capabilities (NetworkPolicies, PSA tightening, Velero, etc.) without rewriting. Companion image for `docs/lab-to-production.md` and the README.

## Command

```bash
gemini -y -p '/generate "Stage-progression architecture diagram for Forjate showing the trajectory Lab to MVP to Production. Three vertical panels arranged side by side, each representing one stage of a Kubernetes cluster running Forjate. Each stage adds components and gates without rewriting the prior. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for stage titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL, STAGE. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

Three vertical rounded rectangles of equal width arranged side by side, separated by thin vertical dotted cyan dividers. Between adjacent rectangles, a small horizontal cyan arrow with the label GROW in tiny amber monospace placed above it.

First rectangle — heading LAB in cyan monospace, large. Subtitle in tiny amber: USD 0 to 5 / month — one node. Hardware icon at the top: a single small server box labeled k3s single node. Below, a stack of small chips representing the active components: Traefik, cert-manager, Longhorn (1 replica), MinIO single-server, GoTrue. A small caption at the bottom of the rectangle in tiny dim cyan monospace reads: learning. weekend projects. demos.

Second rectangle — heading MVP in cyan monospace, large. Subtitle in tiny amber: USD 60 to 150 / month — 3 nodes. Hardware icon at the top: three small server boxes stacked horizontally, joined by a small brace labeled k3s HA. Below, the same chips as Lab PLUS new chips highlighted with amber borders to show they are added at this stage: MetalLB, ArgoCD, Sealed Secrets, Prometheus, Grafana, Cloudflare Tunnel, NetworkPolicy default-deny, PSA baseline, Helm versions pinned. A small caption at the bottom in tiny dim cyan monospace reads: real users. internal tools. early SaaS.

Third rectangle — heading PRODUCTION in cyan monospace, large. Subtitle in tiny amber: USD 200 to 500 / month — HA plus offsite. Hardware icon at the top: three small server boxes plus a small separate cloud-shaped icon labeled offsite backup, all joined by thin lines. Below, the MVP chips PLUS new chips highlighted with magenta borders to show they are added at this stage: Velero (backup and DR), PSA restricted, Postgres operator (CNPG), Image scanning + Cosign, OpenTelemetry full, Crossplane (optional managed services). A small caption at the bottom in tiny dim cyan monospace reads: SLA. compliance. multi-tenant SaaS.

Across the full bottom of the image, a horizontal amber bar in monospace reading FORJATE — START AT LAB. GROW INTO PRODUCTION. SAME BASE. SAME COMPONENTS. JUST MORE OF THEM.

Above the bottom bar, a thin horizontal dim-cyan progress legend reading: cost grows with capability — never with the platform.

A tiny terminal artifact in the bottom-left corner reads > forjate:lab-to-production_v0.1 in cyan monospace. Generous whitespace despite three-panel density. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Final.** Approved on first pass. Used in `docs/lab-to-production.md` and embedded in the root README. |

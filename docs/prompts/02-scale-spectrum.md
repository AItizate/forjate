# 02 — Scale Spectrum

**Output:** `docs/assets/architecture/scale-spectrum.png`
**Aspect:** 16:9
**Approved version:** v0.2

Single image showing the same architecture at four scales, side by side. Same icon language across all four.

## Command (v0.2 — final)

```bash
gemini -y -p '/generate "Side-by-side comparison diagram of the same Kubernetes architecture running at four different scales, for Forjate. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

LAYOUT:
Four vertical panels, equal width, stacked side by side, separated by thin vertical dotted dividers in cyan. Each panel framed by a rounded rectangle with a thin cyan border and the same height. Each panel starts at the top with the panel name as a bold amber monospace heading, followed one line below by a small cyan monospace subtitle. DO NOT render any literal word like Title, Header, or Label — only the panel name itself.

PANEL 1 — heading: SINGLE NODE. subtitle: home / edge — hardware only, ~USD 0/month. Contents: a single rounded rectangle in the center labeled k3s, with chips inside stacked vertically: Traefik, Longhorn, MinIO, Postgres, Home Assistant, OpenClaw, MetalLB, Prometheus, cluster-introspector. Outside the rectangle at the bottom, a small icon labeled NAS connected by a thin dotted line to the k3s box.

PANEL 2 — heading: BARE METAL CLUSTER. subtitle: small rack — predictable cost. Contents: three small stacked rounded rectangles labeled NODE 1, NODE 2, NODE 3, joined by a vertical brace on the left labeled k3s HA. To the right of the nodes, chips listed vertically: Traefik, Longhorn (3 replicas), MetalLB, ArgoCD, Cloudflare Tunnel, Prometheus, Grafana, Sealed Secrets, Zitadel.

PANEL 3 — heading: HYBRID. subtitle: bare metal + cloud burst — same overlay. Contents: on the left a small cluster box labeled BARE METAL with chips Postgres, MinIO inside. On the right a stylized cloud-shaped outline labeled CLOUD BURST with chips managed RDS, S3 inside. Between them a bidirectional horizontal arrow labeled Crossplane in magenta monospace.

PANEL 4 — heading: MULTI-CLOUD PORTABLE. subtitle: equivalent of any hyperscaler VPS. Contents: three small cloud-shaped outlines stacked vertically labeled AWS, GCP, AZURE. Each contains the same identical set of chips: Crossplane, Postgres (managed), Object Storage (managed), Workload Pods. Across the top of the panel, just below the heading and subtitle, an amber horizontal bar reads SAME KUSTOMIZE OVERLAY.

Bottom of the entire image: a single horizontal bar in amber monospace reading THE DIFFERENCE: FIFTY LINES OF YAML, NOT A MIGRATION PROJECT.

A tiny bottom-left corner terminal artifact reads > forjate:scale-spectrum_v0.2 in cyan monospace. Generous whitespace despite the four-panel density. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | Layout solid, but model rendered literal "TITLE BAR" text on each panel header. |
| **v0.2** | **Final.** Removed any "TITLE BAR" wording from the prompt — panels now show their name directly. |

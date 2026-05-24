# 06 — Overlay: bare-metal-starter

**Output:** `docs/assets/architecture/overlay-bare-metal-starter.png`
**Aspect:** 16:9
**Approved version:** v0.2

## Command (v0.2 — final)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the bare-metal-starter overlay of Forjate. A first serious on-prem Kubernetes cluster with a GitOps loop driven by GitHub and ArgoCD. Infrastructure only, no apps deployed yet. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

On the left side of the image, three small stylized server rectangle icons stacked vertically labeled NODE 1, NODE 2, NODE 3, joined by a vertical curly brace on their left edge labeled k3s HA in amber monospace. Below the three nodes, a tiny cyan monospace subtitle: your rack.

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER (bare metal) in amber.

Inside the cluster, four labeled sub-rectangles (capability groups) arranged in a 2x2 grid. Each sub-rectangle has its title as a small bold amber monospace heading and contains its component chips in cyan monospace.

Upper-half-left sub-rectangle — heading INGRESS AND NETWORKING. Chips: Traefik (Ingress Controller), MetalLB (LoadBalancer IPs), cert-manager (TLS via Lets Encrypt).

Upper-half-right sub-rectangle — heading STORAGE. Chips: Longhorn (Replicated Block Storage), MinIO (S3-compatible Object Storage).

Lower-half-left sub-rectangle — heading GITOPS AND SECRETS. Chips: ArgoCD (GitOps Loop), Sealed Secrets (Encrypted in Git), Kustomize (Composition).

Lower-half-right sub-rectangle — heading OBSERVABILITY. Chips: Prometheus (Metrics), Grafana (Dashboards), Reloader (ConfigMap Watcher).

OUTSIDE the cluster on the right side, two stacked external boxes:

Upper external box labeled GITHUB in amber monospace heading. Inside the box, two stacked chips:
- APP REPOS (with CI/CD) — magenta-tinted chip
- IAC REPO — amber-tinted chip
A small internal arrow inside the GITHUB box goes from APP REPOS down to IAC REPO with the label CI updates image tags in tiny cyan monospace.
From the IAC REPO chip, a thin cyan arrow with a faint glow flows LEFTWARD INTO the cluster, terminating exactly at the ArgoCD chip inside the GITOPS AND SECRETS sub-rectangle. Annotation along this arrow in tiny amber monospace: ArgoCD pulls every 3 min.

Lower external box: a small icon labeled INTERNET. From INTERNET, a horizontal arrow flows LEFTWARD into the cluster, terminating at a small magenta chip labeled CLOUDFLARE TUNNEL that sits at the cluster border (acting as a single secure pinhole). From CLOUDFLARE TUNNEL, a thin cyan arrow continues into the Traefik chip inside the INGRESS AND NETWORKING sub-rectangle. Annotation on the external arrow in tiny amber monospace: no open ports.

Below the cluster, a thin horizontal cyan bar spanning the cluster width with text in tiny cyan monospace: YOUR LAN — MetalLB pool reserved outside the DHCP range.

At the very bottom of the image, a single horizontal amber bar in monospace reading BARE-METAL-STARTER — NOTHING FANCY. JUST ENOUGH TO FEEL REAL.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-bare-metal-starter_v0.2 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | 2x2 capability grid + 3 nodes + INTERNET → Cloudflare Tunnel. "Let-s Encrypt" appeared with literal hyphen because of escape. |
| **v0.2** | **Final.** Added GITHUB box (APP REPOS with CI/CD + IAC REPO) with internal arrow showing CI updates image tags and external arrow showing ArgoCD pulls every 3 min. Fixed "Lets Encrypt" (no hyphen). |

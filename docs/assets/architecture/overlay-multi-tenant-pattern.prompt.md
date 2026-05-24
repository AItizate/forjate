# Overlay: multi-tenant-pattern (operational view)

**Output:** `overlay-multi-tenant-pattern.png` (alongside this file)
**Aspect:** 16:9
**Status:** template — not yet generated

Complementary to [`multi-tenant-pattern.prompt.md`](./multi-tenant-pattern.prompt.md). That image is the **conceptual** view (directory tree + composition funnel). This one is the **operational** view — a real cluster running three tenants side by side, showing what's shared vs what's per-tenant, and how ingress reaches each one by subdomain.

## Command (template)

```bash
gemini -y -p '/generate "Operational architecture diagram for the multi-tenant-pattern overlay of Forjate in production. A single Kubernetes cluster running an org overlay with three live tenants in separate namespaces. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

OUTSIDE the cluster on one side, three small chips stacked vertically labeled with subdomains: client-a.example.com, client-b.example.com, client-c.example.com. From each subdomain chip, a separate horizontal arrow flows INTO the cluster, terminating at a single shared chip labeled TRAEFIK (Ingress) at the cluster boundary. Annotation above the three arrows in tiny cyan monospace: TLS via cert-manager.

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER in amber.

Inside the cluster, two distinct zones separated by a thin horizontal dotted divider:

The upper zone is labeled ORG OVERLAY (shared) in amber monospace. Inside it, a horizontal row of chips representing the shared services: TRAEFIK (Ingress), ArgoCD (GitOps), Prometheus (Metrics), Sealed Secrets, Zitadel (SSO). Each chip is in cyan, rendered uniformly to convey that they are platform-wide.

The lower zone is labeled PER-TENANT NAMESPACES in amber monospace. Inside it, three equal-sized sub-rectangles arranged horizontally, separated by thin vertical dotted dividers. Each sub-rectangle has a tenant heading in magenta monospace and contains the same set of per-tenant chips. From the upper zone TRAEFIK chip, three thin cyan arrows fan downward, each terminating at one of the three tenant sub-rectangles, with route labels next to each arrow in tiny cyan monospace.

First tenant sub-rectangle — heading namespace: client-a. Chips inside: app-deployment, postgres-a (StatefulSet), secrets-a (sealed), feature-flag-set: pro.

Second tenant sub-rectangle — heading namespace: client-b. Chips inside: app-deployment, postgres-b (StatefulSet), secrets-b (sealed), feature-flag-set: basic.

Third tenant sub-rectangle — heading namespace: client-c. Chips inside: app-deployment, postgres-c (StatefulSet), secrets-c (sealed), feature-flag-set: enterprise.

Between adjacent tenant sub-rectangles, render a small NetworkPolicy lock icon with a thin red-or-magenta crossed-out arrow connecting them, with annotation in tiny dim cyan monospace: NetworkPolicy deny. This communicates hard isolation between tenants.

At the very bottom of the image, a single horizontal amber bar in monospace reading MULTI-TENANT-PATTERN — ONE ORG OVERLAY. THREE TENANTS. ZERO CODE DUPLICATION.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-multi-tenant-pattern_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| _(none yet)_ | Template only. Run when you want the operational counterpart of the #03 conceptual view. |

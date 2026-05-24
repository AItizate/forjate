# 03 — Multi-Tenant Recursive Pattern

**Output:** `docs/assets/architecture/multi-tenant-pattern.png`
**Aspect:** 16:9
**Approved version:** v0.1

Visualizes the recursive composition: base → org overlay → per-client overlay.

## Command (v0.1 — final)

```bash
gemini -y -p '/generate "Recursive composition diagram showing how the multi-tenant Kustomize pattern repeats from a shared base to N tenants, for Forjate. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels and file paths, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

LAYOUT:
Two roughly equal vertical halves separated by a thin vertical dotted divider in cyan.

LEFT HALF — section heading at the top in bold amber monospace: DIRECTORY TREE. Below the heading, a clean indented directory tree rendered in white cyan monospace with the following structure exactly, each line indented to show hierarchy, with small inline comment-style annotations in dim cyan after a # symbol:

k8s/
  base/                              # Forjate base, never edited per tenant
  components/                        # optional building blocks
  overlays/
    multi-tenant-pattern/
      org/                           # the org overlay
        kustomization.yaml           # pulls base + your common components
      tenants/
        client-a/                    # per-client overlay
          kustomization.yaml         # extends ../../org
          namespace.yaml
          patches/                   # subdomain, replicas, flags
          secrets/                   # sealed, client A only
        client-b/                    # same shape, different values
        client-c/                    # same shape, different values

The org/ line and its kustomization.yaml are highlighted with a subtle amber glow, and the client-a/ line is highlighted with a subtle magenta glow, to draw the eye to the inheritance points.

RIGHT HALF — section heading at the top in bold amber monospace: COMPOSITION. Below the heading, three rounded rectangles stacked vertically, decreasing slightly in width as they go down (suggesting funneling). Each connected to the next by a downward arrow labeled EXTENDS in tiny cyan monospace.

TOP RECTANGLE — labeled FORJATE BASE in cyan. Inside chips: Traefik, cert-manager, Longhorn, MinIO, namespaces. Subtitle below the box in tiny cyan monospace: hardware-agnostic. inherited by everyone.

MIDDLE RECTANGLE — labeled ORG OVERLAY (acme-saas) in amber. Inside chips: Postgres, MinIO patches, GoTrue, ArgoCD, Prometheus, Sealed Secrets, branding patches. Subtitle: your company defaults. defined once.

BOTTOM RECTANGLE — labeled PER-CLIENT OVERLAYS in magenta. Inside, three small mini-rectangles labeled CLIENT A, CLIENT B, CLIENT C with chips inside each: subdomain, feature flags, sealed secrets, replicas. Subtitle: only what changes per client.

Bottom of the entire image: a single horizontal bar in amber monospace reading MULTI-TENANT BY DESIGN — REPEAT THE PATTERN AS MANY TIMES AS YOU HAVE CLIENTS.

A tiny bottom-left corner terminal artifact reads > forjate:multi-tenant_v0.1 in cyan monospace. Generous whitespace despite dense info. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Final.** Approved on first pass. |

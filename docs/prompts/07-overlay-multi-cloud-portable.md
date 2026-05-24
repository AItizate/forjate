# 07 — Overlay: multi-cloud-portable

**Output:** `docs/assets/architecture/overlay-multi-cloud-portable.png`
**Aspect:** 16:9
**Approved version:** v0.1

## Command (v0.1 — final)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the multi-cloud-portable overlay of Forjate. The same Kubernetes application overlay running across bare metal, AWS, GCP, and Azure — identical app deployment, only the StorageClass and the database secret source differ per flavor. Crossplane is the portability seam. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL, FLAVOR. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

At the top of the image, a wide horizontal amber bar spanning most of the width reading SAME APPLICATION DEPLOYMENT — IDENTICAL ACROSS FLAVORS in amber monospace.

From that amber bar, four downward thin cyan arrows fan out into four equal-width vertical rounded rectangles stacked side by side, separated by thin vertical dotted dividers in cyan. Each rectangle has its name as a bold amber monospace heading at its top, with a small cyan monospace subtitle one line below.

First rectangle — heading BARE METAL. subtitle: predictable cost. Chips inside, stacked vertically:
- Longhorn StorageClass
- PostgreSQL (in-cluster)
- MinIO (in-cluster object store)
- Workload Pods

Second rectangle — heading AWS. subtitle: gp3 StorageClass. Chips inside, stacked vertically:
- Crossplane
- provider-aws-rds
- provider-aws-s3
- External Secrets (from AWS Secrets Manager)
- Workload Pods

Third rectangle — heading GCP. subtitle: pd-balanced StorageClass. Chips inside, stacked vertically:
- Crossplane
- provider-gcp-sql
- provider-gcp-storage
- External Secrets (from GCP Secret Manager)
- Workload Pods

Fourth rectangle — heading AZURE. subtitle: managed-csi StorageClass. Chips inside, stacked vertically:
- Crossplane
- provider-azure-postgres
- provider-azure-storage
- External Secrets (from Azure Key Vault)
- Workload Pods

Below the four rectangles, a horizontal cyan callout band spanning the full width with text in cyan monospace: TWO SEAMS OF PORTABILITY — StorageClass + Crossplane-managed services. Smaller annotation below in tiny dim cyan monospace: the app reads a Postgres connection string. it does not know who provisioned it.

At the very bottom of the image, a single horizontal amber bar in monospace reading MULTI-CLOUD-PORTABLE — ONE OVERLAY. THREE PROVIDERS. ZERO MIGRATIONS.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-multi-cloud-portable_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Final.** Approved on first pass. Bootstrap caveat (Crossplane needs an existing cluster) is documented in `docs/overlays/multi-cloud-portable.md` rather than rendered in the image, to keep the diagram focused on the steady-state portability story. |

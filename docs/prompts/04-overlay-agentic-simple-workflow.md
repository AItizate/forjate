# 04 — Overlay: agentic-simple-workflow

**Output:** `docs/assets/architecture/overlay-agentic-simple-workflow.png`
**Aspect:** 16:9
**Approved version:** v0.3

## Command (v0.3 — final)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the agentic-simple-workflow overlay of Forjate. Shows multiple entry channels, the agent as a hub with verb-labeled tool spokes, external LLM providers, an example pipeline, and backup destinations. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. DO NOT render literal layout words like ENTRY or CENTER COLUMN or RIGHT COLUMN — let the section names (HUMAN UI, CHANNELS, KUBERNETES CLUSTER, OUTBOUND AND BACKUP, EXTERNAL LLM PROVIDERS) speak for themselves. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

LAYOUT:
TOP STRIP across the full width of the image, ABOVE the cluster — a thin horizontal rounded rectangle labeled EXTERNAL LLM PROVIDERS in amber monospace. Inside it, four chips in a row: AWS Bedrock, GCP Vertex AI, Azure OpenAI, Private GPU. A single downward arrow with faint cyan glow exits this strip and enters the cluster pointing at the LiteLLM chip inside. Label on the arrow in tiny cyan monospace: route via LiteLLM.

LEFT COLUMN about 18 percent of width — two vertically stacked rounded rectangles:
- Top rectangle labeled HUMAN UI in cyan: a small user icon and a chip labeled DASHBOARD / APP. A horizontal arrow goes right INTO the cluster but is intercepted by a thin vertical magenta-tinted gate at the cluster edge, labeled AUTHZ (Zitadel + GoTrue + OAuth2 Proxy).
- Bottom rectangle labeled CHANNELS in cyan: three chat-bubble chips labeled SLACK, TELEGRAM, OTHER. A horizontal arrow goes right INTO the cluster bypassing the AUTHZ gate, with annotation in tiny cyan: channel-side auth.

CENTER about 50 percent of width — a large rounded rectangle labeled KUBERNETES CLUSTER (k3s) in amber at the top.

Inside the cluster, in the dead center, a prominent magenta hexagonal chip labeled AGENT (large, the visual focal point). Five spokes radiate from AGENT to surrounding tool chips. Each spoke is a thin cyan bidirectional arrow with a verb label in tiny cyan monospace placed along the line:
- Spoke to TEMPORAL (Durable Workflows) — label: orchestrates
- Spoke to LiteLLM + vLLM (Inference Gateway) — label: infers
- Spoke to LanceDB / Milvus (Vector Store for RAG) — label: retrieves
- Spoke to PostgreSQL (state and memory) — label: persists
- Spoke to MinIO (artifacts and run logs) — label: stores

Arrange the five tool chips around the AGENT in a balanced star pattern.

Across the BOTTOM of the cluster, a horizontal pipeline strip with a tiny cyan monospace title PIPELINE EXAMPLE above it. The strip shows five small chips connected by right-pointing arrows: LinkedIn Source → Ingest → Prospects DB → RAG → Mail Proposals. The last arrow exits the cluster to the right.

RIGHT COLUMN about 18 percent of width — a rounded rectangle labeled OUTBOUND AND BACKUP in cyan at the top. Three stacked items:
- Top: a chip labeled MAIL TO CLIENTS receiving the arrow exiting from the pipeline strip.
- Middle: a chip labeled S3 (cloud) with an arrow coming from MinIO inside the cluster, labeled nightly backup in tiny amber monospace.
- Bottom: a chip labeled EXTERNAL DISK (via Longhorn) with another arrow from MinIO, labeled mirror in tiny amber monospace.

Bottom of the entire image: a single horizontal bar in amber monospace reading AGENTIC-SIMPLE-WORKFLOW — INPUT FROM ANYWHERE, INFER ANYWHERE, PERSIST EVERYWHERE.

A tiny bottom-left corner terminal artifact reads > forjate:overlay-agentic-simple_v0.3 in cyan monospace. Generous whitespace despite dense info. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | Topology-only. Static rows (ingress, runtime, state) with a USER on left and a CRONJOB backup on right. Rejected — did not communicate what the overlay actually does as a product. |
| v0.2 | Restructured as agent-hub + tool spokes + multiple entry channels + outbound backups. Pipeline example added. Spokes labeled by geometry (UP-LEFT, RIGHT, etc.) — wrong. |
| **v0.3** | **Final.** Added EXTERNAL LLM PROVIDERS strip on top (AWS Bedrock, GCP Vertex AI, Azure OpenAI, Private GPU). vLLM replaces Ollama in the inference gateway chip. Spokes relabeled by verb (orchestrates, infers, retrieves, persists, stores). Layout labels (ENTRY/CENTER COLUMN/RIGHT COLUMN) removed. One small visual quirk: LiteLLM rendered twice — accepted, not worth another iteration. |

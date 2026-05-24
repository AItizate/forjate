# 01 — Reference Architecture

**Output:** `docs/assets/architecture/reference-architecture.png`
**Aspect:** 16:9
**Approved version:** v0.4

## Command (v0.4 — final)

```bash
gemini -y -p '/generate "Conceptual enterprise architecture diagram for Forjate, a Kubernetes infrastructure factory. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. Everything readable. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

LAYOUT:
LEFT VERTICAL COLUMN about 16 percent of width labeled EXTERNAL SOURCE LAYER at the top. Vertical stack of chips below: External CRM, External SaaS, Legacy Data, IoT Devices and Sensors, Third-party APIs.

To the RIGHT of that External column is the CENTER STACK (the main cluster), occupying about 64 percent of width. It contains 5 horizontal rounded rectangle rows stacked top to bottom:

1) EDGE AND ACCESS row: chips Traefik (Ingress), Zitadel + GoTrue + OAuth2 Proxy (SSO), Istio (Service Mesh), Custom BFF.

2) LOGIC AND AI row: chips Temporal (Durable Workflows), LiteLLM + vLLM + Ollama (Inference Gateway), OpenClaw + n8n + Node-RED (Agents).

3) INGESTION row labeled INGESTION (ELT / ETL): chips Airbyte (ELT), dbt (ETL). This is where the External Source arrow lands.

4) A SHARED HORIZONTAL BAR labeled MinIO — Object Storage and Data Lake Foundation. This bar visually BRIDGES the row above (Ingestion) and the row below (Data Layer): its top border merges with the bottom of the Ingestion row, and its bottom border merges with the top of the Data Layer row. Add small bracket-style markers or dotted hairlines on its left and right edges that wrap both upward and downward, making it visually obvious that this bar BELONGS TO BOTH the ingestion and the data layers. Also add a small label on the right side of the bar that reads SHARED in tiny amber monospace.

5) DATA LAYER row: four grouped sub-sections separated by thin vertical dividers:
   - Medallion (Bronze MinIO, Silver PostgreSQL, Gold MongoDB / dbt marts)
   - AI Knowledge Bases (LanceDB, Milvus, Knowledge Graph)
   - Cache and Metadata (Redis, etcd)
   - Change Data Capture (Debezium → RabbitMQ / NATS)

A single thick horizontal arrow with a faint cyan glow flows rightward from the EXTERNAL SOURCE column straight INTO the INGESTION row (row 3 of the center stack). The arrow does NOT touch any other row. Above the arrow add a small label INGEST in tiny cyan monospace.

Thin dotted vertical connectors between the other center-stack rows suggest data flowing down.

RIGHT VERTICAL SIDEBAR about 16 percent of width labeled CROSS-CUTTING. Three stacked sections, each item rendered as its own small chip:
- OBSERVABILITY: Prometheus, Grafana, OpenTelemetry, Reloader.
- GITOPS AND IAC: ArgoCD, Kustomize, Crossplane, Sealed Secrets, External Secrets, Vault.
- MLOPS: Model Registry, OTA Updates.

A tiny bottom-left corner terminal artifact reads > forjate:reference-arch_v0.4 in cyan monospace. Generous whitespace despite dense info. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | First pass. External Source as top row. Components were generic (no concrete tool names). Rejected — wanted concrete components and a different flow shape. |
| v0.2 | External as left vertical column. ELT/ETL as labels above a single arrow that ran all the way to Logic & AI. Debezium mixed into ingestion. Rejected — CDC doesn't belong with batch ingest; ingestion should be its own labeled stop. |
| v0.3 | External + Ingestion both as separate left columns. Ingestion holds Airbyte + dbt. Debezium moved into Data Layer as "Change Data Capture" subsection. Rejected — wanted Ingestion to live inside the center stack and MinIO to visually bridge Ingestion and Data. |
| **v0.4** | **Final.** Ingestion is now a row inside the center stack. MinIO is a SHARED horizontal bar with brackets/dotted edges that visually belongs to both Ingestion (above) and Data Layer (below). Arrow from External terminates at the Ingestion row only. |

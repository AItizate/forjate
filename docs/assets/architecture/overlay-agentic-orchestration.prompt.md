# Overlay: agentic-orchestration

**Output:** `overlay-agentic-orchestration.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.2

Two entry paths: chat channels (Telegram, WhatsApp) reach an Agent that can answer directly or delegate to a durable Temporal workflow; traditional triggers (HTTP webhooks, cron) reach Temporal directly. A Worker container polls Temporal and executes the registered workflows.

## Command (v0.2 — final)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the agentic-orchestration overlay of Forjate. Two entry paths into the cluster: chat channels (Telegram, WhatsApp) reach an Agent that can either answer directly or delegate to a durable Temporal workflow; traditional triggers (HTTP webhooks, cron) reach Temporal directly for batch and scheduled work. A Worker container polls Temporal and executes the registered workflows, calling LiteLLM for inference and persisting outputs to MongoDB. Postgres holds Temporal workflow state. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

On the left side of the image, two vertically stacked rounded rectangles:

The first one labeled CHANNELS in cyan. Inside: two chat-bubble chips labeled TELEGRAM and WHATSAPP. From each chip, a separate horizontal arrow flows rightward into the cluster, both terminating at the AGENT chip inside. Annotation along these arrows in tiny cyan monospace: bot webhooks.

The second one labeled TRIGGERS in cyan. Inside: two stacked chips HTTP / Webhook and Scheduled (cron). From each chip, an arrow flows rightward into the cluster, both terminating at the TEMPORAL SERVER chip inside. Annotation in tiny cyan monospace: starts workflows.

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER — namespace: agentic in amber.

Inside the cluster:

In the upper-middle area, a prominent amber chip labeled TEMPORAL SERVER (the orchestration brain). A downward bidirectional cyan arrow connects TEMPORAL SERVER to POSTGRESQL (workflow state and history) below it, with label persists workflow state in tiny cyan monospace.

In the dead center on the left half of the cluster interior, a prominent magenta hexagonal chip labeled AGENT (chat-facing focal point). The AGENT has these connections:
- Bidirectional cyan arrow to TEMPORAL SERVER above it — label: starts + signals workflows
- Bidirectional cyan arrow rightward to LiteLLM (in a small sub-box labeled namespace: ai-tools) — label: infers
- Bidirectional cyan arrow downward to MONGODB — label: chat memory

In the dead center on the right half of the cluster interior, an amber rounded-rectangle chip labeled WORKER (your container). The WORKER has these connections:
- Bidirectional cyan arrow upward to TEMPORAL SERVER — label: polls + executes
- Bidirectional cyan arrow leftward to LiteLLM (same ai-tools sub-box that AGENT talks to) — label: infers
- Bidirectional cyan arrow downward to MONGODB — label: dumps results
- Cyan arrow downward to POSTGRESQL — label: reads workflow context

Place the LiteLLM ai-tools sub-box on the far upper-right inside the cluster as a clearly-labeled small sub-rectangle (separate from the agentic namespace contents). Use a thin dotted vertical divider inside the cluster between the agentic contents and the ai-tools sub-box to suggest the namespace boundary.

Place MONGODB as a single chip in the lower-middle of the cluster, shared by both AGENT (chat memory) and WORKER (workflow outputs).

OUTSIDE the cluster on the right side, a small rounded rectangle labeled TEMPORAL UI containing a chip Workflow Inspector. A thin cyan arrow from TEMPORAL SERVER flows rightward to TEMPORAL UI, passing through a thin magenta-tinted gate at the cluster edge labeled OAuth2 Proxy.

Across the bottom of the cluster, a horizontal cyan callout band with text in cyan monospace: chat-first agent. delegates the heavy lifting to durable workflows.

At the very bottom of the image, a single horizontal amber bar in monospace reading AGENTIC-ORCHESTRATION — CONVERSATIONAL + DURABLE.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-agentic-orchestration_v0.2 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | TRIGGERS-only entry (HTTP, cron, signal) → TEMPORAL → WORKER hub. Missing the conversational entry point. Rejected because it didn't reflect how the overlay is actually used: AGENT receives chat from external channels and decides whether to answer directly or delegate to a durable workflow. |
| **v0.2** | **Final.** Added AGENT as the chat-facing focal point. Added CHANNELS box (Telegram, WhatsApp) feeding the AGENT. AGENT can start + signal Temporal workflows. WORKER kept as the workflow executor. Both AGENT and WORKER share LiteLLM (ai-tools namespace) and MongoDB (chat memory vs workflow outputs). |

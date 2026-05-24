# Overlay: cdc-event-sourcing

**Output:** `overlay-cdc-event-sourcing.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.1

Change Data Capture from MongoDB replica set into RabbitMQ via Debezium. Validation Job proves the pipeline end-to-end.

## Command

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the cdc-event-sourcing overlay of Forjate. A Change Data Capture pipeline that watches a MongoDB replica set and emits every change as a typed message into RabbitMQ via Debezium. Ships with a post-deploy validation Job that proves the pipeline works end-to-end. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM, GROUP, PANEL. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):

On the left side of the image, a rounded rectangle labeled APPLICATIONS in cyan. Inside, a stack of chips: Write API, Mobile Backend, Batch Importer. A single thick cyan arrow flows rightward into the cluster, terminating at MONGODB inside. Annotation along the arrow in tiny cyan monospace: writes.

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER — namespace: event-sourcing in amber.

Inside the cluster, three chips arranged in a horizontal CDC pipeline flow from left to right, each connected to the next by a thick cyan arrow with a verb label in tiny cyan monospace:

First chip on the left of the cluster: MONGODB (replica set), magenta-bordered to emphasize the source. Subtitle in tiny dim cyan monospace: oplog enabled.

Arrow from MONGODB to the next chip — label: tails oplog.

Middle chip: DEBEZIUM (CDC Connector), amber-bordered. Subtitle: translates oplog into typed messages.

Arrow from DEBEZIUM to the next chip — label: emits.

Right chip in the pipeline: RABBITMQ (Message Broker). Subtitle: at-least-once delivery.

Below the pipeline, slightly offset, a smaller magenta-bordered chip labeled cdc-validate (Job). A thin dotted cyan curve from this chip touches both MONGODB and RABBITMQ with the label runs post-deploy. writes + asserts. exits non-zero on failure in tiny dim cyan monospace.

OUTSIDE the cluster on the right side, a rounded rectangle labeled CONSUMERS in cyan. Inside, three stacked chips: Analytics Sink, Notification Worker, Audit Log. A single thick cyan arrow flows rightward from RABBITMQ inside the cluster to CONSUMERS, passing through a thin magenta-tinted gate at the cluster edge labeled OAuth2 Proxy (admin UI only) — but the message stream itself bypasses the gate via a separate arrow labeled AMQP.

Across the bottom of the cluster, a horizontal cyan callout band with text in cyan monospace: single source of truth. no dual-write drift. replayable.

At the very bottom of the image, a single horizontal amber bar in monospace reading CDC-EVENT-SOURCING — WRITE ONCE. STREAM EVERYWHERE.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-cdc-event-sourcing_v0.1 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| **v0.1** | **Final.** Approved on first pass. Original prompt had AMQP path crossing the OAuth2 Proxy gate by mistake — fixed before generation: AMQP to consumers bypasses the gate; only the Mgmt Console UI sits behind it. |

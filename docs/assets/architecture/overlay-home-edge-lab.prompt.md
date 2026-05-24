# Overlay: home-edge-lab

**Output:** `overlay-home-edge-lab.png` (alongside this file)
**Aspect:** 16:9
**Approved version:** v0.4

## Command (v0.4 — final)

```bash
gemini -y -p '/generate "Single-overlay architecture diagram for the home-edge-lab overlay of Forjate. A real Kubernetes platform on one Raspberry Pi 5 and a household NAS. Family interacts via dashboard or chat channels (Telegram, WhatsApp). Home Assistant runs the home. OpenClaw agent inside the cluster talks to Home Assistant and answers family chat. Single 16:9 wide cinematic frame. Cyberpunk dystopian terminal aesthetic — dark deep-navy background #0A1428 with very subtle horizontal scanlines and faint grain noise. Cyan #5BB4FF primary accents, occasional magenta #FF5BBF and warm amber #FFB45B highlights on key labels. Monospace terminal-style font for chip labels, slightly bolder geometric sans for section titles. Slightly imperfect borders with subtle 1-2px chromatic drift on a few boxes. NO PHOTOS NO 3D NO LOGOS NO COMPANY NAMES NO WATERMARK.

CRITICAL: do NOT render any of these words anywhere in the image: LEFT, RIGHT, CENTER, COLUMN, GATE, SECTION, ROW, LAYOUT, AREA, UPPER, LOWER, TOP, BOTTOM. Only render actual content labels.

LAYOUT (instructions for you only, do not write these on the image):
At the top-left corner, a small hardware inventory callout: two minimalistic icon boxes labeled RASPBERRY PI 5 and HOUSEHOLD NAS connected by a thin horizontal line. Subtitle in tiny cyan monospace: the entire platform.

On the left side of the image, two stacked rounded rectangles:

The first one has the heading FAMILY ACCESS in cyan. Inside: a small user icon, then three stacked chips: DASHBOARD (Home Assistant UI), TELEGRAM, WHATSAPP. From DASHBOARD, one horizontal arrow goes right toward the cluster, passing through two adjacent thin vertical bars at the cluster edge — first a cyan-tinted bar with CLOUDFLARE TUNNEL written inside, then immediately a magenta-tinted bar with OAuth2 Proxy + GoTrue written inside. From TELEGRAM and from WHATSAPP, two separate arrows go RIGHT AND SLIGHTLY DOWNWARD, bypass those bars, and travel along the bottom edge of the cluster, terminating clearly and visibly at the chip OPENCLAW AGENT located in the bottom-center of the cluster. Annotation along those two arrows in tiny cyan monospace: bot webhooks. Make it visually unambiguous that those two arrows reach OPENCLAW AGENT and nothing else.

The second one has the heading IOT INPUTS in cyan. Inside: four chips stacked vertically: Temperature Sensors, IP Cameras, ESP32 Devices, Smart Plugs. A single horizontal arrow goes right and terminates at the MOSQUITTO chip inside the cluster. Annotation in tiny cyan: MQTT.

In the middle of the image, a large rounded rectangle. Its top reads KUBERNETES CLUSTER (k3s on Pi + NAS) in amber.

Inside the cluster, in the upper-middle area (not at the bottom), a prominent magenta hexagonal chip labeled HOME ASSISTANT — the central focal point of the cluster. Five spokes radiate outward from HOME ASSISTANT to surrounding chips, each spoke a thin cyan bidirectional arrow with a verb label in tiny cyan monospace:
- to MOSQUITTO (MQTT Broker) — label: listens. MOSQUITTO is ONLY connected to HOME ASSISTANT. No other arrow touches MOSQUITTO from inside the cluster.
- to ESPHOME (Device Firmware) — label: flashes
- to NODE-RED (Automations) — label: triggers
- to MARIADB (Long-term Metrics) — label: persists
- to MINIO (Camera Clips and Backups) — label: stores

In the bottom-center of the cluster (clearly below the HOME ASSISTANT star pattern, with breathing space), one prominent chip rendered in amber labeled OPENCLAW AGENT with subtitle in tiny cyan monospace: chat + observer + control. Exactly ONE single bidirectional cyan arrow connects OPENCLAW AGENT to HOME ASSISTANT, with the verb label observes + controls placed once along it. One dotted cyan arrow from OPENCLAW AGENT extends to the inner edge of the cluster rectangle with the label read-only ClusterRole. No other arrows touch OPENCLAW AGENT from inside.

On the right side of the image, a rounded rectangle with the heading PHYSICAL OUTPUTS in cyan at the top. Three stacked items:
- chip SMART DEVICES (lights, plugs, blinds) receiving an arrow from NODE-RED, labeled control in tiny amber monospace.
- chip FAMILY NOTIFICATIONS (push) receiving an arrow from HOME ASSISTANT, labeled alert in tiny amber monospace.
- chip BACKUPS (NAS + optional S3) receiving an arrow from MINIO, labeled mirror in tiny amber monospace.

The bottom of the entire image shows a single horizontal bar in amber monospace reading HOME-EDGE-LAB — A REAL PLATFORM ON A SHELF, RUNNING ON A PI AND A NAS.

A tiny terminal artifact in the bottom-left corner reads > forjate:overlay-home-edge_v0.4 in cyan monospace. Generous whitespace. Polished but with a hint of late-night sysadmin gloom."'
```

## Iteration log

| Version | Notes |
|---------|-------|
| v0.1 | Topology decent but small typo "Az2 Proxy" and gate labels duplicated. Did not include OpenClaw agent or chat channels. |
| v0.2 | Added OPENCLAW AGENT inside cluster, added TELEGRAM + WHATSAPP in FAMILY ACCESS. Model rendered literal LEFT COLUMN / CENTER / RIGHT COLUMN as visible text. |
| v0.3 | Removed literal layout words. Cleaner. Bot webhook arrows still ambiguous — appeared to end at Home Assistant, not OpenClaw. Postgres still present. |
| **v0.4** | **Final.** Postgres → MariaDB. Mosquitto explicitly only connected to HOME ASSISTANT. OPENCLAW AGENT relocated to bottom-center with breathing space. Telegram/WhatsApp arrows clearly route along the bottom edge to OPENCLAW AGENT. Single labels per connection. |

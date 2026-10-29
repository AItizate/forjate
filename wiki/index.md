---
title: index
kind: index
compiled_at: '2026-10-29'
---

# Forjate wiki — index

Content-oriented catalog of the whole wiki. **Agents: read this page first**, find the relevant entries, then open those pages.

Everything under `base/`, `components/` and `overlays/` is compiled from `k8s/**` by `scripts/wiki-compile.py`. Pages under `concepts/` are written by agents and hold synthesis that no single directory contains.

Conventions and maintenance rules: [SCHEMA.md](SCHEMA.md) · History: [log.md](log.md) · Built on [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## Concepts

- [component-anatomy](concepts/component-anatomy.md) — what a component is made of, local vs vendored, and how nesting shows up in the wiki
- [multi-tenant-recursion](concepts/multi-tenant-recursion.md) — base to org to client composition, and how the tree demonstrates it
- [remote-references](concepts/remote-references.md) — how tenants consume the factory by SSH ref, and where pinning is inconsistent
- [secret-strategy](concepts/secret-strategy.md) — five mechanisms coexist; external-secrets syncing from openbao is the recommended store pairing; who uses what

## Base

The foundation every tenant inherits.

- [base](base/base.md) — declares `Certificate`, `Namespace`
- [cert-manager](base/cert-manager.md) — vendors `cert-manager.crds.yaml`
- [minio](base/minio.md) — vendors `operator`
- [oauth2-proxy](base/oauth2-proxy.md) — declares `Ingress`, `Middleware`
- [traefik](base/traefik.md) — deploys `docker.io/traefik:v3.5.2`

## Components

79 pages. Optional building blocks an overlay can activate.

### agents

- [agents-cluster-introspector](components/agents-cluster-introspector.md) — deploys `busybox:1.37` · used by 1

### ai-models

- [ai-models-litellm](components/ai-models-litellm.md) — deploys `ghcr.io/berriai/litellm:main-stable` · used by 5
  - [ai-models-litellm-postgres](components/ai-models-litellm-postgres.md) — composes `postgres` · used by 2
- [ai-models-ollama](components/ai-models-ollama.md) — deploys `ollama/ollama:latest` · used by 4
- [ai-models-open-webui](components/ai-models-open-webui.md) — deploys `ghcr.io/open-webui/open-webui:main` · used by 1
- [ai-models-vllm](components/ai-models-vllm.md) — deploys `vllm/vllm-openai:latest` · used by 2

### analytics

- [analytics-metabase](components/analytics-metabase.md) — Metabase — open-source BI and analytics platform · unused in this repo

### auth

- [auth-gotrue-auth](components/auth-gotrue-auth.md) — Gotrue Auth — Google OAuth authentication and authorization with per-app RBAC · used by 4
  - [auth-gotrue-auth-authz](components/auth-gotrue-auth-authz.md) — deploys `node:20.18-alpine` · used by 1
  - [auth-gotrue-auth-gotrue](components/auth-gotrue-auth-gotrue.md) — deploys `busybox:1.36` · used by 1
  - [auth-gotrue-auth-middlewares](components/auth-gotrue-auth-middlewares.md) — declares `Middleware` · used by 1

### brokers

- [brokers-mosquitto](components/brokers-mosquitto.md) — deploys `eclipse-mosquitto` · used by 1
- [brokers-nats](components/brokers-nats.md) — NATS 2.10 with JetStream — lightweight message streaming with persistence · unused in this repo
- [brokers-rabbitmq](components/brokers-rabbitmq.md) — RabbitMQ 3.13 — AMQP broker with Streams support · used by 1

### bundles

- [bundles-temporal-stack](components/bundles-temporal-stack.md) — temporal-stack — Temporal + PostgreSQL in a single reference · used by 1

### cdc

- [cdc-debezium-mariadb-nats](components/cdc-debezium-mariadb-nats.md) — Debezium Server — MariaDB Binlog → NATS JetStream CDC · unused in this repo
- [cdc-debezium-mariadb-rabbitmq](components/cdc-debezium-mariadb-rabbitmq.md) — Debezium Server — MariaDB Binlog → RabbitMQ CDC · unused in this repo
- [cdc-debezium-mongo-nats](components/cdc-debezium-mongo-nats.md) — Debezium Server — MongoDB Change Streams → NATS JetStream CDC · unused in this repo
- [cdc-debezium-mongo-rabbitmq](components/cdc-debezium-mongo-rabbitmq.md) — Debezium Server — MongoDB Change Streams → RabbitMQ CDC · used by 1
- [cdc-debezium-postgres-nats](components/cdc-debezium-postgres-nats.md) — Debezium Server — PostgreSQL Logical Replication → NATS JetStream CDC · unused in this repo
- [cdc-debezium-postgres-rabbitmq](components/cdc-debezium-postgres-rabbitmq.md) — Debezium Server — PostgreSQL Logical Replication → RabbitMQ CDC · unused in this repo

### communication

- [communication-snappymail](components/communication-snappymail.md) — Snappymail — lightweight webmail client (IMAP/SMTP) · unused in this repo
- [communication-stalwart](components/communication-stalwart.md) — Stalwart Mail Server - SMTP/IMAP/JMAP mail & collaboration server · unused in this repo

### continuous-delivery

- [continuous-delivery-argocd](components/continuous-delivery-argocd.md) — vendors `install.yaml` · used by 4

### databases

- [databases-etcd](components/databases-etcd.md) — deploys `quay.io/coreos/etcd:v3.5.16` · used by 1
- [databases-lancedb](components/databases-lancedb.md) — deploys `setchevest/lancedb-server:0.4.6` · unused in this repo
- [databases-mariadb](components/databases-mariadb.md) — deploys `linuxserver/mariadb` · unused in this repo
- [databases-milvus](components/databases-milvus.md) — deploys `milvusdb/milvus:v2.5.4` · used by 1
- [databases-mongodb](components/databases-mongodb.md) — MongoDB 7 — base standalone (without replica set) · used by 3
  - [databases-mongodb-replica-set](components/databases-mongodb-replica-set.md) — MongoDB replica set enabler — applied on top of databases/mongodb via components: · used by 1 as component
- [databases-postgres](components/databases-postgres.md) — PostgreSQL 16 — generic reusable database component · used by 9
- [databases-redis](components/databases-redis.md) — deploys `redis:7-alpine` · used by 1

### document-processing

- [document-processing-docling](components/document-processing-docling.md) — deploys `ghcr.io/docling-project/docling-serve-cpu:latest` · used by 1

### home-automation

  - [home-automation-esphome](components/home-automation-esphome.md) — deploys `esphome/esphome:latest` · used by 1
  - [home-automation-hass](components/home-automation-hass.md) — deploys `homeassistant/raspberrypi4-homeassistant:latest` · used by 1

### iac

- [iac-crossplane](components/iac-crossplane.md) — Crossplane: a Kubernetes-native control plane to declare cloud resources · unused in this repo

### minio

- [minio-dev](components/minio-dev.md) — deploys `docker.io/bitnamilegacy/minio:2025.7.23` · used by 1
- [minio-single-server](components/minio-single-server.md) — deploys `quay.io/minio/minio:latest` · used by 6

### monitoring

- [monitoring-grafana](components/monitoring-grafana.md) — deploys `grafana/grafana:11.6.0` · used by 4
- [monitoring-kubernetes-dashboard](components/monitoring-kubernetes-dashboard.md) — declares `ClusterRoleBinding`, `Ingress`, `Secret` · unused in this repo
- [monitoring-otel-collector](components/monitoring-otel-collector.md) — composes `agent`, `cluster` · used by 1
  - [monitoring-otel-collector-agent](components/monitoring-otel-collector-agent.md) — deploys `otel/opentelemetry-collector-contrib:0.98.0` · used by 1
  - [monitoring-otel-collector-cluster](components/monitoring-otel-collector-cluster.md) — deploys `otel/opentelemetry-collector-contrib:0.98.0` · used by 1
- [monitoring-prometheus](components/monitoring-prometheus.md) — deploys `prom/prometheus:v3.2.1` · used by 6
- [monitoring-reloader](components/monitoring-reloader.md) — Stakater Reloader — auto-restarts Deployments/StatefulSets on Secret/ConfigMap changes · used by 2

### n8n

  - [n8n-n8n](components/n8n-n8n.md) — deploys `busybox:1.36` · used by 1
  - [n8n-postgres](components/n8n-postgres.md) — deploys `postgres:15` · used by 1

### networking

- [networking-metallb](components/networking-metallb.md) — vendors `native?ref=v0.15.2` · used by 3

### productivity

- [productivity-affine](components/productivity-affine.md) — AFFiNE — open-source Notion + Miro alternative with built-in AI · unused in this repo
  - [productivity-affine-server](components/productivity-affine-server.md) — deploys `busybox:1.36` · used by 1
- [productivity-appflowy](components/productivity-appflowy.md) — AppFlowy Cloud - collaborative workspace (Notion alternative) · unused in this repo
  - [productivity-appflowy-admin-frontend](components/productivity-appflowy-admin-frontend.md) — deploys `appflowyinc/admin_frontend:0.13.3` · used by 1
  - [productivity-appflowy-ai](components/productivity-appflowy-ai.md) — deploys `appflowyinc/appflowy_ai:0.13.3` · used by 1
  - [productivity-appflowy-appflowy-cloud](components/productivity-appflowy-appflowy-cloud.md) — deploys `appflowyinc/appflowy_cloud:0.13.3` · used by 1
  - [productivity-appflowy-gotrue](components/productivity-appflowy-gotrue.md) — deploys `appflowyinc/gotrue:0.13.3` · used by 1
  - [productivity-appflowy-search](components/productivity-appflowy-search.md) — deploys `appflowyinc/appflowy_search:0.13.3` · used by 1
  - [productivity-appflowy-web](components/productivity-appflowy-web.md) — deploys `appflowyinc/appflowy_web:0.13.3` · used by 1
  - [productivity-appflowy-worker](components/productivity-appflowy-worker.md) — deploys `appflowyinc/appflowy_worker:0.13.3` · used by 1

### pvcs

- [pvcs](components/pvcs.md) — declares `PersistentVolumeClaim` · unused in this repo

### pvs

- [pvs-local-storage](components/pvs-local-storage.md) — declares `PersistentVolume` · unused in this repo
- [pvs-nfs-storage](components/pvs-nfs-storage.md) — declares `PersistentVolume` · unused in this repo

### rbac

- [rbac](components/rbac.md) — declares `ClusterRole`, `ClusterRoleBinding`, `ServiceAccount` · used by 1

### security

- [security-external-secrets](components/security-external-secrets.md) — External Secrets Operator (ESO) — syncs secrets from external stores · used by 2
- [security-openbao](components/security-openbao.md) — secret store (MPL-2.0, Vault API): raft, audit to stdout, kubernetes/approle/userpass auth and an SSH CA after bootstrap.sh · used by 1
  - [security-openbao-eso-store](components/security-openbao-eso-store.md) — OpenBao as an External Secrets store — applied on top of security/openbao via components: · used by 1 as component
  - [security-openbao-follow-namespace](components/security-openbao-follow-namespace.md) — transformer, not a component: makes security-openbao follow an overlay's namespace: (CRB subject, eso-store server) · used by 1 as transformer
  - [security-openbao-raft-snapshot](components/security-openbao-raft-snapshot.md) — OpenBao raft snapshots — applied on top of security/openbao via components: · used by 1 as component
  - [security-openbao-seal-static](components/security-openbao-seal-static.md) — OpenBao static-key auto-unseal — applied on top of security/openbao via components: · used by 1 as component
- [security-vault](components/security-vault.md) — deprecated in favour of security-openbao: `hashicorp/vault:1.19` (BUSL-1.1), file storage, no unseal story · unused in this repo

### standalone

- [cloudflare-tunnel](components/cloudflare-tunnel.md) — deploys `cloudflare/cloudflared:latest` · used by 3
- [docker-registry](components/docker-registry.md) — deploys `registry:2` · unused in this repo
- [home-automation](components/home-automation.md) — composes `esphome`, `hass` · used by 1
- [n8n](components/n8n.md) — composes `postgres`, `n8n` · unused in this repo
- [node-red](components/node-red.md) — deploys `busybox:1.36` · used by 2
- [sealed-secrets](components/sealed-secrets.md) — vendors `controller.yaml` · used by 7
- [whoami](components/whoami.md) — deploys `traefik/whoami` · used by 1

### storage

- [storage-longhorn](components/storage-longhorn.md) — vendors `longhorn.yaml` · used by 4

### surveys

- [surveys-formbricks](components/surveys-formbricks.md) — deploys `ghcr.io/formbricks/formbricks:latest` · used by 1

### workflows

- [workflows-temporal](components/workflows-temporal.md) — Temporal — workflow orchestration engine (server + UI) · used by 1

## Overlays

Concrete environments assembled from base + components.

- [agentic-orchestration](overlays/agentic-orchestration.md) — Agentic Orchestration — multi-agent workflow pattern · 5 local references
- [agentic-simple-workflow](overlays/agentic-simple-workflow.md) — Smallest production-shaped overlay for a single agentic workload · 6 local references
- [ai-dev-stack](overlays/ai-dev-stack.md) — declares `ClusterIssuer`, `Namespace` · 11 local references
- [bare-metal-starter](overlays/bare-metal-starter.md) — Starter overlay for a first serious bare-metal cluster · 7 local references
- [cdc-event-sourcing](overlays/cdc-event-sourcing.md) — deploys `mongo:7` · 6 local references
- [home-edge-lab](overlays/home-edge-lab.md) — Home automation + IoT + cameras + an agent gateway on a Raspberry Pi and a NAS · 14 local references
- [multi-cloud-portable](overlays/multi-cloud-portable.md) — Bare-metal flavor of the multi-cloud-portable overlay · 5 local references
- [multi-tenant-pattern-org](overlays/multi-tenant-pattern-org.md) — The "org overlay" — your company's standard shape on top of Forjate's base · 7 local references
- [multi-tenant-pattern-tenants-client-a](overlays/multi-tenant-pattern-tenants-client-a.md) — Per-client overlay. Extends the org overlay (../../org) and applies only · 1 local reference
- [multi-tenant-pattern-tenants-client-b](overlays/multi-tenant-pattern-tenants-client-b.md) — declares `Namespace` · 1 local reference
- [quickstart](overlays/quickstart.md) — deploys `curlimages/curl:8.10.1` · 3 local references
- [usecases-db-migration-a-to-b](overlays/usecases-db-migration-a-to-b.md) — deploys `busybox:1.36` · 3 local references
- [usecases-invoice-intake](overlays/usecases-invoice-intake.md) — Crawl root of invoice-intake, assembled from .builder/ by forjate:kustomize. Stages extend it: stages/walk, stages/run · 5 local references
- [usecases-invoice-intake-stages-run](overlays/usecases-invoice-intake-stages-run.md) — run stage of invoice-intake: extends ../walk and adds what the records require for run, nothing the plan put out of scope · 4 local references
- [usecases-invoice-intake-stages-walk](overlays/usecases-invoice-intake-stages-walk.md) — walk stage of invoice-intake: recomposes the Crawl root (base, Crawl components, the namespace child) and adds what the records require for walk, nothing the plan put out of scope · 13 local references
- [usecases-openbao-secrets](overlays/usecases-openbao-secrets.md) — ephemeral end-to-end proof of security-openbao: static unseal, raft snapshots, External Secrets store, a Kubernetes and an AppRole agent; run in CI · 2 local references
- [usecases-openbao-secrets-openbao](overlays/usecases-openbao-secrets-openbao.md) — security-openbao with all four sub-directories, moved to namespace `openbao` the way a tenant does it · 5 local references
- [usecases-support-copilot](overlays/usecases-support-copilot.md) — Crawl root of support-copilot, assembled from .builder/ by forjate:kustomize. Stages extend it: stages/walk, stages/run · 3 local references
- [usecases-support-copilot-stages-walk](overlays/usecases-support-copilot-stages-walk.md) — walk stage of support-copilot: recomposes the Crawl root (base, Crawl components, the namespace child) and adds what the records require for walk, nothing the plan put out of scope · 11 local references

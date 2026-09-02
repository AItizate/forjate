---
title: index
kind: index
compiled_at: '2026-09-02'
---

# Forjate wiki — index

Content-oriented catalog of the whole wiki. **Agents: read this page first**, find the relevant entries, then open those pages.

Everything under `base/`, `components/` and `overlays/` is compiled from `k8s/**` by `scripts/wiki-compile.py`. Pages under `concepts/` are written by agents and hold synthesis that no single directory contains.

Conventions and maintenance rules: [SCHEMA.md](SCHEMA.md) · History: [log.md](log.md) · Built on [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## Concepts

- [component-anatomy](concepts/component-anatomy.md) — what a component is made of, local vs vendored, and how nesting shows up in the wiki
- [multi-tenant-recursion](concepts/multi-tenant-recursion.md) — base to org to client composition, and how the tree demonstrates it
- [remote-references](concepts/remote-references.md) — how tenants consume the factory by SSH ref, and where pinning is inconsistent
- [secret-strategy](concepts/secret-strategy.md) — four mechanisms coexist; which overlays use which, and what is declared but unused

## Base

The foundation every tenant inherits.

- [base](base/base.md) — deploys `docker.io/traefik:v3.5.2`
- [cert-manager](base/cert-manager.md) — vendors `cert-manager.crds.yaml`
- [minio](base/minio.md) — composes `operator`
- [oauth2-proxy](base/oauth2-proxy.md) — declares `Ingress`, `Middleware`
- [traefik](base/traefik.md) — deploys `docker.io/traefik:v3.5.2`

## Components

74 pages. Optional building blocks an overlay can activate.

### agents

- [agents-cluster-introspector](components/agents-cluster-introspector.md) — deploys `busybox:1.37` · used by 1

### ai-models

- [ai-models-litellm](components/ai-models-litellm.md) — deploys `ghcr.io/berriai/litellm:main-stable` · unused in this repo
  - [ai-models-litellm-postgres](components/ai-models-litellm-postgres.md) — composes `postgres` · unused in this repo
- [ai-models-ollama](components/ai-models-ollama.md) — deploys `ollama/ollama:latest` · used by 1
- [ai-models-open-webui](components/ai-models-open-webui.md) — deploys `ghcr.io/open-webui/open-webui:main` · unused in this repo
- [ai-models-vllm](components/ai-models-vllm.md) — deploys `vllm/vllm-openai:latest` · unused in this repo

### analytics

- [analytics-metabase](components/analytics-metabase.md) — deploys `metabase/metabase:v0.59.6` · unused in this repo

### auth

- [auth-gotrue-auth](components/auth-gotrue-auth.md) — deploys `busybox:1.36` · used by 3
  - [auth-gotrue-auth-authz](components/auth-gotrue-auth-authz.md) — deploys `node:20.18-alpine` · used by 1
  - [auth-gotrue-auth-gotrue](components/auth-gotrue-auth-gotrue.md) — deploys `busybox:1.36` · used by 1
  - [auth-gotrue-auth-middlewares](components/auth-gotrue-auth-middlewares.md) — declares `Middleware` · used by 1

### brokers

- [brokers-mosquitto](components/brokers-mosquitto.md) — deploys `eclipse-mosquitto` · used by 1
- [brokers-nats](components/brokers-nats.md) — deploys `nats:2.10-alpine` · unused in this repo
- [brokers-rabbitmq](components/brokers-rabbitmq.md) — deploys `rabbitmq:3.13-management` · unused in this repo

### bundles

- [bundles-temporal-stack](components/bundles-temporal-stack.md) — composes `postgres`, `temporal` · unused in this repo

### cdc

- [cdc-debezium-mariadb-nats](components/cdc-debezium-mariadb-nats.md) — deploys `natsio/nats-box:0.19` · unused in this repo
- [cdc-debezium-mariadb-rabbitmq](components/cdc-debezium-mariadb-rabbitmq.md) — deploys `quay.io/debezium/server:3.4` · unused in this repo
- [cdc-debezium-mongo-nats](components/cdc-debezium-mongo-nats.md) — deploys `natsio/nats-box:0.19` · unused in this repo
- [cdc-debezium-mongo-rabbitmq](components/cdc-debezium-mongo-rabbitmq.md) — deploys `quay.io/debezium/server:3.4` · unused in this repo
- [cdc-debezium-postgres-nats](components/cdc-debezium-postgres-nats.md) — deploys `natsio/nats-box:0.19` · unused in this repo
- [cdc-debezium-postgres-rabbitmq](components/cdc-debezium-postgres-rabbitmq.md) — deploys `quay.io/debezium/server:3.4` · unused in this repo

### communication

- [communication-snappymail](components/communication-snappymail.md) — deploys `djmaze/snappymail:v2.38.2` · unused in this repo
- [communication-stalwart](components/communication-stalwart.md) — deploys `busybox:1.36` · unused in this repo

### continuous-delivery

- [continuous-delivery-argocd](components/continuous-delivery-argocd.md) — vendors `install.yaml` · used by 2

### databases

- [databases-etcd](components/databases-etcd.md) — deploys `quay.io/coreos/etcd:v3.5.16` · unused in this repo
- [databases-lancedb](components/databases-lancedb.md) — deploys `setchevest/lancedb-server:0.4.6` · unused in this repo
- [databases-mariadb](components/databases-mariadb.md) — deploys `linuxserver/mariadb` · unused in this repo
- [databases-milvus](components/databases-milvus.md) — deploys `milvusdb/milvus:v2.5.4` · unused in this repo
- [databases-mongodb](components/databases-mongodb.md) — deploys `busybox` · unused in this repo
  - [databases-mongodb-replica-set](components/databases-mongodb-replica-set.md) — deploys `busybox` · unused in this repo
- [databases-postgres](components/databases-postgres.md) — deploys `postgres:16` · used by 6
- [databases-redis](components/databases-redis.md) — deploys `redis:7-alpine` · unused in this repo

### document-processing

- [document-processing-docling](components/document-processing-docling.md) — deploys `ghcr.io/docling-project/docling-serve-cpu:latest` · unused in this repo

### home-automation

  - [home-automation-esphome](components/home-automation-esphome.md) — deploys `esphome/esphome:latest` · used by 1
  - [home-automation-hass](components/home-automation-hass.md) — deploys `homeassistant/raspberrypi4-homeassistant:latest` · used by 1

### iac

- [iac-crossplane](components/iac-crossplane.md) — declares `Account`, `Bucket`, `DatabaseInstance` · unused in this repo

### minio

- [minio-dev](components/minio-dev.md) — deploys `quay.io/minio/minio:latest` · unused in this repo
- [minio-single-server](components/minio-single-server.md) — deploys `quay.io/minio/minio:latest` · used by 4

### monitoring

- [monitoring-grafana](components/monitoring-grafana.md) — deploys `grafana/grafana:11.6.0` · used by 2
- [monitoring-kubernetes-dashboard](components/monitoring-kubernetes-dashboard.md) — declares `ClusterRoleBinding`, `Ingress`, `Secret` · unused in this repo
- [monitoring-otel-collector](components/monitoring-otel-collector.md) — deploys `otel/opentelemetry-collector-contrib:0.98.0` · unused in this repo
  - [monitoring-otel-collector-agent](components/monitoring-otel-collector-agent.md) — deploys `otel/opentelemetry-collector-contrib:0.98.0` · used by 1
  - [monitoring-otel-collector-cluster](components/monitoring-otel-collector-cluster.md) — deploys `otel/opentelemetry-collector-contrib:0.98.0` · used by 1
- [monitoring-prometheus](components/monitoring-prometheus.md) — deploys `prom/prometheus:v3.2.1` · used by 4
- [monitoring-reloader](components/monitoring-reloader.md) — Stakater Reloader — auto-restarts Deployments/StatefulSets on Secret/ConfigMap changes · unused in this repo

### n8n

  - [n8n-n8n](components/n8n-n8n.md) — deploys `busybox:1.36` · used by 1
  - [n8n-postgres](components/n8n-postgres.md) — deploys `postgres:15` · used by 1

### networking

- [networking-metallb](components/networking-metallb.md) — vendors `native?ref=v0.15.2` · used by 2

### productivity

- [productivity-affine](components/productivity-affine.md) — deploys `busybox:1.36` · unused in this repo
  - [productivity-affine-server](components/productivity-affine-server.md) — deploys `busybox:1.36` · used by 1
- [productivity-appflowy](components/productivity-appflowy.md) — deploys `appflowyinc/admin_frontend:0.13.3` · unused in this repo
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

- [security-external-secrets](components/security-external-secrets.md) — declares `Namespace` · unused in this repo
- [security-vault](components/security-vault.md) — deploys `hashicorp/vault:1.19` · unused in this repo

### standalone

- [cloudflare-tunnel](components/cloudflare-tunnel.md) — deploys `cloudflare/cloudflared:latest` · used by 2
- [docker-registry](components/docker-registry.md) — deploys `registry:2` · unused in this repo
- [home-automation](components/home-automation.md) — deploys `esphome/esphome:latest` · used by 1
- [n8n](components/n8n.md) — deploys `busybox:1.36` · unused in this repo
- [node-red](components/node-red.md) — deploys `busybox:1.36` · used by 1
- [sealed-secrets](components/sealed-secrets.md) — vendors `controller.yaml` · used by 5
- [whoami](components/whoami.md) — deploys `traefik/whoami` · unused in this repo

### storage

- [storage-longhorn](components/storage-longhorn.md) — vendors `longhorn.yaml` · used by 2

### surveys

- [surveys-formbricks](components/surveys-formbricks.md) — deploys `ghcr.io/formbricks/formbricks:latest` · unused in this repo

### workflows

- [workflows-temporal](components/workflows-temporal.md) — deploys `temporalio/auto-setup:latest` · used by 1

## Overlays

Concrete environments assembled from base + components.

- [agentic-orchestration](overlays/agentic-orchestration.md) — deploys `registry.example.com/temporal-worker:latest` · 3 local references
- [agentic-simple-workflow](overlays/agentic-simple-workflow.md) — Smallest production-shaped overlay for a single agentic workload · 6 local references
- [ai-dev-stack](overlays/ai-dev-stack.md) — declares `Certificate`, `ClusterIssuer`, `Deployment` · 5 local references
- [bare-metal-starter](overlays/bare-metal-starter.md) — Starter overlay for a first serious bare-metal cluster · 7 local references
- [cdc-event-sourcing](overlays/cdc-event-sourcing.md) — deploys `mongo:7` · 3 local references
- [home-edge-lab](overlays/home-edge-lab.md) — Home automation + IoT + cameras + an agent gateway on a Raspberry Pi and a NAS · 14 local references
- [multi-cloud-portable](overlays/multi-cloud-portable.md) — Bare-metal flavor of the multi-cloud-portable overlay · 5 local references
- [multi-tenant-pattern-org](overlays/multi-tenant-pattern-org.md) — The "org overlay" — your company's standard shape on top of Forjate's base · 7 local references
- [multi-tenant-pattern-tenants-client-a](overlays/multi-tenant-pattern-tenants-client-a.md) — Per-client overlay. Extends the org overlay (../../org) and applies only · 1 local reference
- [multi-tenant-pattern-tenants-client-b](overlays/multi-tenant-pattern-tenants-client-b.md) — declares `Namespace` · 1 local reference
- [quickstart](overlays/quickstart.md) — deploys `curlimages/curl:8.10.1` · 2 local references
- [usecases-db-migration-a-to-b](overlays/usecases-db-migration-a-to-b.md) — deploys `busybox:1.36` · 2 local references

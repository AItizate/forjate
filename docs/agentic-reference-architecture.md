# Agentic reference architecture

What a production agentic system on Forjate looks like, in two views: the seven layers an enterprise expects to see, and the six layers a request actually flows through. Both are deliberately abstract; the last section maps them to the catalog as it stands today, and only there do component names appear.

The idea in one sentence: **one spine, N components.** Every layer is exposed the same way, as a GitOps-managed component behind the ingress, callable over MCP or REST. Adding an agent, a tool or a knowledge source reuses the same ingress, auth and observability spine every other component already uses. That reuse is what lets a small team stand up a production stack in weeks instead of assembling bespoke integrations per layer.

## The seven layers (what an organisation gets)

| Layer | What it is | Builder expert that owns it |
|-------|------------|-----------------------------|
| 1. Secure access | Infosec-approved sandbox, identity, RBAC enforced at the ingress for every request, network boundaries, in week one not at the end | security, devops |
| 2. Unified data | Fragmented sources (databases, CRMs, wikis, mailboxes) brought into one governed foundation | data-pipeline, data-store |
| 3. Knowledge | The organisation's context compiled into source-traceable, cross-linked knowledge agents can cite, not fragments retrieved at query time; runtime retrieval where compilation does not apply | data-store, ai-engineering |
| 4. Agentic | Domain agents that each own one capability, an orchestrator that coordinates without owning business logic, human oversight at defined points | ai-engineering, architecture |
| 5. Process wiring | Agents connected to the live interfaces of the business (chat, ticketing, ERP, portals) through standard APIs, replacing manual handoffs with digital execution | architecture, ux |
| 6. Production and governance | CI/CD, GitOps, drift monitoring, guardrails, audit trail, scaling | quality, devops, compliance |
| 7. Transfer | Side-by-side operation, governance playbook, certified handover; the tenant owns and runs everything | business, coordinator |

## The six layers a request flows through (how it runs)

1. **Entry and access control.** Every call hits the ingress first and is enriched with identity and permissions before it reaches any agent or service. One choke point for access control across the whole stack; revoking a permission there is the kill switch.
2. **Reasoning core.** The agent's model call goes through one gateway that routes to the right model (local or external) by policy, enforces cost budgets, applies guardrails and emits telemetry. One control plane, not four tools.
3. **Planning and orchestration.** A durable workflow engine decomposes the goal into steps, tracks state, survives restarts, and bounds execution (steps, timeouts, delegation depth). This is what turns one model call into a resumable multi-step run; individual model calls stay stateless, the run is stateful.
4. **Knowledge, memory and retrieval.** When the agent needs context it asks the knowledge layer over MCP. Memory is scoped (session, user, project, organisation) and anchored to governed knowledge so it does not drift into a private, unverifiable accumulation.
5. **Tools and actions.** Agents reach external systems through registered tools with strict schemas, an intent-validation step before execution, and human approval for writes until autonomy has been earned. Any tool is just another service behind the ingress.
6. **Operational layer and governance.** Every step is GitOps-managed, so state is reproducible from git; every action leaves an audit record (prompt, model and version, tool call and parameters, cost, duration, approvals); human gates are designed to validate, not confirm.

## Autonomy is a staged decision

| Stage | Autonomy | What has to be true |
|-------|----------|---------------------|
| Crawl | assistive: the agent recommends, a person acts | the reasoning is proven on real-shaped data in a disposable environment |
| Walk | semi-autonomous: the agent executes registered tools, writes need approval | real users, measured accuracy against a golden set, audit trail in place |
| Run | autonomous for the actions the evidence supports | drift monitoring, kill switch rehearsed, compliance signed, autonomy increases approved one by one starting read-only |

Autonomy never increases by default. Each increase is a gate with an owner, and the use-case builder's `gates.yaml` is where it is recorded.

## What the catalog resolves this to today

A snapshot, not a rule. The use-case builder picks components by role from `wiki/catalog.json`; this table shows what those roles resolve to at the time of writing so a reader can picture the stack.

| Layer | Roles | Today |
|-------|-------|-------|
| Entry and access | `ingress`, `auth`, `identity` | Traefik, oauth2-proxy, GoTrue |
| Reasoning core | `llm-gateway`, `model-routing`, `cost-tracking`, `inference`, `local-model` | LiteLLM in front of Ollama or vLLM, or an external provider when egress is allowed |
| Planning and orchestration | `durable-workflows`, `orchestration`, `messaging` | Temporal (as `bundles/temporal-stack`), NATS |
| Knowledge and memory | `session-memory`, `long-term-memory`, `semantic-memory`, `vector`, `artifacts`, `document-parsing` | Redis, Postgres, LanceDB or Milvus, MinIO, Docling; a knowledge compiler implementing the LLM Wiki pattern is not in the catalog yet |
| Tools and actions | `cdc`, `audit-trail`, `low-code-automation` | Debezium connectors, n8n or Node-RED for glue; tools are the use case's own code behind MCP |
| Operations and governance | `gitops`, `secrets-mechanism`, `secrets-store`, `metrics`, `dashboards`, `telemetry` | ArgoCD, Sealed Secrets then External Secrets pulling from OpenBao, Prometheus, Grafana, OpenTelemetry collector |

Gaps this view exposes, tracked as catalog backlog: a knowledge compiler component, a structured per-tool-call audit ledger over OpenTelemetry, an evaluation harness component. Until they exist, the builder's records name them as gates and open questions, never as capabilities.

## Where this came from

Distilled from the "Enterprise Agent Architecture in a Box" synthesis and an enterprise RFI response (2026), both written for a client proposal. The governance posture they describe is available to the use-case builder as the context pack `context-packs/examples/enterprise-in-a-box`, so any use case can be held to it without editing a skill. Related: `docs/architecture-overview.md` for the infrastructure factory underneath, `docs/use-case-builder/` for how a use case is planned against these layers.

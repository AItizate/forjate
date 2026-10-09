# Model governance

Model access is centralised behind one gateway with routing, budgets, guardrails and telemetry; agents never call a provider directly. That single point is where governance lives.

- **Register, not catalog.** No fixed list of models; a governance register per category (foundation, embedding, reranker, OCR, safety) records provider, deployment option, pinned version, hosting region and data-handling terms. Compliance owns the register; AI engineering fills it.
- **Allow-list, versioned and reviewed.** Only approved models route; fallback goes to another approved-tier model, never downgrades automatically.
- **Pinning and upgrade gate.** Versions are pinned in configuration. A provider update, deprecation or fine-tune change is evaluated against the approved baseline and the use case's eval set, passes a human gate, and is rolled back as a configuration change if behaviour shifts.
- **Routing by policy.** Per agent or step: risk tier, cost and latency, data sensitivity, jurisdiction, residency, language. Sensitive workloads route to local models; lower-risk steps may use external ones under budgets. Every call is traced.
- **Supply-chain risk.** Retirement, policy and residency changes are absorbed as reviewed configuration changes at the gateway; degraded service is caught by drift monitoring. There is no automated supply-chain feed; say so.

# Audit artifacts per agent action

The decision trace of a claim, an order, a transaction or an incident has to be reconstructable after the fact. That is only possible if every agent action logs the same record.

Per action: input or subject; prompts, masked where the data class requires; model and version; tool or integration call with parameters and result; intermediate reasoning artifacts; output; cost; duration; status; timestamps. Plus, per run: OpenTelemetry traces of every interaction and guardrail outcome, the resumable execution history of each orchestration step, and the governance record of each human gate (reviewer, decision, timestamp).

Retention follows the organisation's policy per data domain and is exportable by design: open observability standards and configuration as code mean history is an export, not a feature request.

What the reference architecture does **not** have yet, and must therefore appear as a gate and an open question in the records: a dedicated structured audit trail per tool call. End-to-end flow tracking plus human gates cover governance by process; the per-call ledger is built per program. Do not describe it as present.

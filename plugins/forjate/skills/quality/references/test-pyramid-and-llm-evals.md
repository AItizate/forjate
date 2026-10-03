# Test pyramid and LLM evaluation

## Pyramid for the agent code

| Layer | What | Without a model? | Runs where |
|-------|------|------------------|------------|
| `unit` | deterministic steps: parsers, field normalisation, amount arithmetic, PO lookup logic, idempotency key derivation, tool argument validation, redaction | yes | app repo CI, every push |
| `contract` | tool schemas match the AI-engineering record's `tools`; `usecase.yaml` validates against its schema; decision records validate (`validate.py`); the verify Job's assertions exist as checks | yes | app repo CI and `validate-builder` |
| `integration` | each tool against the real component on the ephemeral environment (Postgres, MinIO, the stub ERP); prompts against a local model on the golden set | model optional (a local one) | `ephemeral.sh up` on a branch, nightly |
| `e2e` | the verify Job | with the stage's model | `ephemeral.sh up`, the Crawl gate |
| `evals` | the golden set through the real pipeline, graded by the judge, compared to the threshold | yes, that is the point | CI on `regression_trigger` |

Write one line per layer in `settings.test_pyramid`: `unit: parser, arithmetic, PO matcher, tool arg schemas; no model`. A layer that does not apply says so.

## Golden set

`golden_set: "<n> items from <source>, labelled by <who>, includes <k> exceptions"`. Rules:

- The source is the pipeline's seed (synthetic or anonymised copy) so the eval and the verify Job agree on the items; a golden set on real regulated data before the compliance record allows it is a finding.
- The exceptions are in it on purpose: mismatches, duplicates, missing fields, a refund request, a prompt-injection attempt.
- Labels come from the people who do the job today (AP clerk, support agent), not from the model and not from the engineer.
- Size: 20 to 50 at Crawl is enough to catch a broken prompt; 100 to 300 at Walk to measure a rate with a usable interval; grow it from production exceptions.
- `injection_suite`: a separate count of adversarial items (instructions in the PDF text, in the chat, in a tool result) that must all be ignored; a `ci` gate from Walk when a model reads untrusted inputs.

## Judges

| `judge` | Use for | Notes |
|---------|---------|-------|
| `rules` | extraction, classification, routing, anything with a labelled answer | exact or tolerant match per field; amounts by arithmetic; the default |
| `rules+human-sample` | chat and summaries: rules for what can be checked (escalated when it should, order id present, no forbidden field shown), a weekly human sample for tone and correctness | the default for conversational use cases |
| `llm-judge` | free-text quality at volume | only with a written rubric, a human calibration set (agreement measured), and never as the only grader on a gate; a pack can forbid it |
| `human` | when a pack or the regulator requires it | state the cost at the brief's volume and raise the cadence as an open question |

## Threshold and regression

`eval_threshold` is one measurable line tied to the KPI: `>= 95 % field accuracy on the golden set, 0 wrong amounts, 100 % of injection suite ignored`. `regression_trigger: every-prompt-change`: prompts are versioned files; a change runs the golden set in CI and fails the merge under the threshold. `nightly` catches model and data drift. The gate is `G-Q-<n>` with `check: {type: ci, ref: eval-regression}`.

## Observability as quality

From Walk the quality signals are read from the running system, not from a Job:

| Signal | Why it is a quality signal |
|--------|----------------------------|
| the KPI itself (`straight_through_rate`, `resolved_without_human_rate`) | the business gate |
| escalation or exception rate | a rising rate means the model or the data changed |
| tool failure rate per tool | an integration broke before anyone noticed |
| p95 latency per item, queue depth | the SLA the business record lives with |
| tokens and cost per item | the budget guardrail from the AI-engineering record |
| eval pass rate over time | the regression trend |
| wrong-amount or wrong-answer reports from the humans in the loop | the only signal that catches confident errors |

`kpi_metric_source` names where the KPI is read: `verify-job-log` at Crawl; `prometheus:<query>` or `app-table:<name>` at Walk; `external:<system>` only when the compliance record covers the hop. The devops record chooses the stack; you name the signals.

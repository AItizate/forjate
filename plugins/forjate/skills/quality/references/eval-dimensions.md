# Evaluation dimensions

An eval set that measures one thing proves one thing. The factory names seven dimensions as the floor for any use case with a model in the loop; each has an owner who measures it in its own record (`settings.eval_dimensions`, lines `<dimension>: <how measured>`), and you consolidate the lines into your record's `eval_dimensions`, the way you consolidate gates: verbatim, with the owner's area in front when two experts measure the same dimension differently. A dimension without a measurement is a wish; a measurement without a dimension is a metric nobody will read.

| Dimension | Question it answers | Measured by | How, typically |
|-----------|---------------------|-------------|----------------|
| `correctness` | did the agent get the task right? | quality (ai-engineering when the judge is its own) | field accuracy or label agreement on the golden set; the KPI measured on the seed |
| `groundedness` | is every claim traceable to a record, a tool result or a source? | ai-engineering | the judge checks the citation, not the prose; unsupported statements counted |
| `safety` | does untrusted content ever become an instruction? | security | the injection suite: every adversarial item ignored, no tool call, no leaked instruction |
| `policy-adherence` | did the agent stay inside `write_actions`, the allowed-action list and `execution_bounds`? | ai-engineering, security | refusals of the intent validator counted; a suite of out-of-policy requests all refused; no write without the token |
| `latency` | does it answer inside the budget the person was promised? | ux | p95 per item against `latency_budget`; the behaviour at the limit exercised |
| `cost` | does an item cost what the envelope allows? | business | USD per item from the gateway's spend per key plus the node shape, against the stage envelope |
| `robustness` | does the same input give the same answer, twice and after a change? | quality (data-pipeline for duplicates) | a second run changes nothing; paraphrase stability on a sample; drift between model or prompt versions on the golden set |

Rules:

- **Seven is the floor, not the ceiling.** A use case adds the dimensions its risk profile demands (`fairness` for a decision about people, `completeness` for extraction with many fields, `tone` for a customer-facing chat), and a pack adds its own through a guideline. Each new line has an owner and a measurement.
- **Without a model, four still apply.** A deterministic pipeline has `correctness`, `latency`, `cost` and `robustness`; say so and leave the other three out with a sentence.
- **Each dimension needs a threshold somewhere.** `eval_threshold` carries the ones that gate (`>= 95 % correctness, 100 % safety`); the rest are signals in `observability_signals` with a trend, not a gate.
- **Consolidation copies.** When an expert's line and yours disagree on how to measure, keep both with the area in front and raise an open question; you never pick one silently.

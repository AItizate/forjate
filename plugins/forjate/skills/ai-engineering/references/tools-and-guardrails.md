# Tools and guardrails

## Tool contract rules

Every line in `settings.tools` is `<name>: <verb> <object> [read-only|idempotent]` and obeys these rules; the app-scaffold skill implements them literally. A pack tool-development guideline adds to this list and never removes from it.

- **Typed in and out.** Arguments and result have a schema; the model never receives a free-form blob it has to parse.
- **Read-only or idempotent, declared.** `lookup_po: read PO by number [read-only]`. `post_invoice: create payable in ERP [idempotent]` with the idempotency key named in `rationale` (supplier + invoice number).
- **Bounded.** Timeout, max result size, pagination. A tool that can return 40k customers returns a page.
- **Least privilege.** Each tool has its own credential scoped to its verb. The agent has no admin credential anywhere.
- **Logged.** Name, argument hash, caller, duration, outcome. Argument values only for `none`/`internal` data classes.
- **Fails loud.** Typed errors the model can act on; never an empty result that looks like "nothing found".
- **Gated writes.** A tool that writes to a system of record or sends a message to a person is callable only with an approval token or a deterministic check result, and the line says which: `post_invoice: create payable in ERP [idempotent, requires approval token]`.

## Guardrail checklist

Write each as one line in `settings.guardrails`, grouped by prefix.

| Prefix | Items |
|--------|-------|
| `input:` | untrusted content delimited as data; instructions inside it ignored by policy; size limits; file type allowlist |
| `output:` | schema validation on structured outputs; allowed-action list; amounts and ids checked against the source of truth before use; refusal path for out-of-scope requests |
| `budget:` | max tool calls per request; max tokens; timeout; max cost per request at the gateway |
| `escalation:` | the conditions that send the item to a human with full context (mismatch, low confidence, refund or cancellation intent, any write the policy gates) |
| `privacy:` | fields never placed in the prompt (bank account numbers, full card numbers), redaction before logging |

## Untrusted inputs

List them in `settings.untrusted_inputs`. Anything a third party authored is untrusted: invoice PDFs, emails, chat messages, web pages, documents from a shared drive, results from external APIs the organisation does not control. The structural defence: the model sees untrusted content inside a clearly delimited data block, the system prompt states that instructions inside data are ignored, and no write tool is reachable in a turn that only saw untrusted content without a deterministic check or a human in between. "The model is told to be careful" is not a guardrail.

## Human-in-the-loop

The business record's exceptions list says who handles what today. Each becomes an `escalation:` guardrail and a gate on the corresponding write tool. The UX expert decides the surface the human sees; you decide that the agent cannot proceed without the token the surface issues.

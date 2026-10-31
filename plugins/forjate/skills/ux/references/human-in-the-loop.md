# Human-in-the-loop checkpoints

## Where checkpoints come from

| Source | Becomes |
|--------|---------|
| business `as_is_exceptions` ("amount differs: finance ops chases the supplier") | one checkpoint per exception, with the person who handles it today |
| AI-engineering `tools` lines ending `[requires approval token]` | exactly one checkpoint that issues that token, naming the tool |
| AI-engineering `guardrails` `escalation:` lines (refund intent, low confidence, two unresolved turns) | one `[deterministic]` checkpoint each |
| security `tool_write_gate: human-approval` | confirms the token checkpoints exist; `deterministic-check` means no person approves and the checkpoint is a handoff |
| the stage plan's exit criteria owned by `ux` | the gate that proves the checkpoint works (usually the escalation context assertion) |

## The line

`<checkpoint-name>: <who> <decides what> <where> [token|deterministic]`

- `[token]`: a person approves or rejects; the surface issues the token the write tool requires; name the tool. `mismatch-approval: the AP clerk approves or rejects an invoice whose amount differs from the PO, in the review queue; approval issues the token post_to_erp requires [token]`.
- `[deterministic]`: a rule routes the item to a person, who then works it in their own tool; nobody approves the handoff. `refund-or-cancellation: always handed to a support agent with the transcript; the bot never promises an outcome [deterministic]`.

Rules:

- Every `[requires approval token]` tool has one `[token]` checkpoint; a tool with two is ambiguous, a tool with none is a write that nobody approves (finding, open question to the AI-engineering expert).
- A handoff is never gated on a human: "a human approves the escalation" is circular. The escalation is the handoff.
- A checkpoint says what the person sees. A clerk approving an amount needs the extracted amount, the PO amount, the difference and the PDF; an agent receiving a refund needs the transcript, the order id and the reason. That is `escalation_context`, and the verify Job asserts it on the seeded exceptions.
- Crawl has no `[token]` checkpoints (nothing real is written); it has the context shape and the verify assertion. The first token appears with the first real write, at Walk.

## Review that validates

Every `[token]` checkpoint states its `review_mode` and `review_independence`. `evidence-first`: the person sees the inputs (the PDF, the transcript), the sources consulted (the PO, the order), the reasoning path (which rule fired, which fields disagreed) and the recommendation last; the escalation context lists them in that order and the verify Job asserts they are present. `independent` where the decision is regulated or irreversible: the reviewer records their own call before the agent's is revealed, and the disagreement is logged with the trace, so the eval set grows from the cases the agent got wrong with confidence. The thresholds that trigger a `[deterministic]` handoff (confidence, amount, risk score, PII detected, budget) are named next to the checkpoint and reviewed; "the agent decides when to escalate" is not a criterion.

## Control by persona

`control_levels` has one line per human actor: `AP clerk: approve` (their token unlocks the write), `finance ops lead: direct, audit` (changes thresholds, reads every decision), `platform operator: operate` (pause, cancel, override a running process, with reviewer, decision and timestamp captured). The security record turns the lines into RBAC and IdP groups; a persona that can both approve and change the thresholds that route items to them is a separation-of-duties risk you name.

## Escalation context

One line listing the fields a person receives when an item is handed over. The verify Job checks each seeded exception against it, so be concrete: `review_queue row: invoice id, supplier, extracted fields, PO fields side by side, reason, PDF object reference`. Missing one of those at Walk means the clerk opens three tools to decide.

## Onboarding and the walkthrough

A surface nobody was shown is a surface nobody uses. Before real users:

- a **walkthrough** on the seeded exception set with the real end-users (clerks, agents), 30 minutes, the ux gate is their sign-off recorded in the Walk report by the requester (`manual`, signer named);
- or a **shadow period** for a bot: its answers are mirrored to the agents' queue before it replies alone, one week, the gate is the agents' sign-off on handoff quality.

`onboarding` is one line; the gate carries the signer. Adoption is a `manual` gate because it is a judgement by the people who will live with the surface, which is the one kind of manual gate that is a decision and not a gap.

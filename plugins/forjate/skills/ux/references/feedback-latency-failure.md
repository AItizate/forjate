# Feedback, latency and failure UX

## Feedback capture per surface

| Surface | `feedback_capture` | How |
|---------|--------------------|-----|
| `cli` / `none` (Crawl) | `verify-job-log` | the requester reads the exceptions and the KPI line; the labels they correct are the feedback |
| `custom-web`, the `chat-ui` component | the `feedback` component (its catalog name; in `choice` from the stage the catalog marks fit) | one question after the action that matters (was the extraction right? was this answer useful?), optional free text, skippable, weekly summary to the requester |
| `chat-channel` | `in-channel` | an inline reaction under each answer (thumbs, a keyboard), written to the outcome row the KPI query reads; never a link to a survey page |
| a review queue | `review-queue-flag` | a "wrong extraction" or "bad answer" flag on the item, which is also the eval corpus growing |
| `existing-tool`, `api-only` | `none` or what the tool offers | say which |

One question per interaction. The response rate is a `metric` gate (`feedback_response_rate`), the negative rate another (`feedback_negative_rate`); both are read from the outcome table, and the quality record's weekly human sample is what keeps a thumbs rate honest. The feedback component is never chosen at Crawl (the catalog marks it fit from Walk, and nobody is there to ask) and never for a chat user.

## Latency budget

Write a sentence with numbers and a behaviour at the limit:

| Shape | Budget | At the limit |
|-------|--------|--------------|
| batch | the run Job's timeout from `usecase.yaml`; nobody waits | the Job fails loudly; items not processed are listed |
| queue | the refresh interval (the mailbox poll, the schedule); extraction is asynchronous, the person sees finished items | an item slower than the interval shows "awaiting extraction", then lands in review with the reason |
| chat | typing indicator immediately; first reply within 5 s; per-turn p95 from the AI-engineering `budget:` guardrail (often 20 s) | past the budget the bot says it is still checking, then hands over with a reason |
| token stream | first token within 2 s, then streaming | a stall past 10 s becomes the chat limit above |

`streaming`: `none` for batch and queues, `typing-indicator` for chat channels (Telegram and Slack support it, email does not), `token-stream` only where the surface renders it (the chat-ui component, a custom page over the gateway). The AI-engineering record's "40 s per invoice on CPU" is not a latency problem for a queue and is a disaster for a chat; say which shape you are in.

## Failure catalogue

Every failure the other records name gets a `failure_ux` line: `<failure>: <what the person sees>, <where the item lands>`.

| Failure (source) | What the person sees | Where the item lands |
|------------------|----------------------|----------------------|
| parse failure (pipeline `dead_letter`) | the item with reason=parse-failed; the clerk can type the fields | review queue |
| model timeout (AI-engineering `budget:`) | "still checking" then a handoff; or the item with reason=timeout | review queue or agent queue, reason recorded |
| tool or system of record down (architecture `integrations`) | "I cannot read your order right now, a colleague will follow up"; or the item with the error text and a retry status | escalation with reason=lookup-failed; the item stays in the queue |
| posting failed (ERP error) | the item back in the queue with the error, retried with the same idempotency key | queue |
| webhook outage (architecture `trigger: chat`) | nothing: the channel retries; replies keyed by message id so no duplicate appears | received-updates table |
| not signed in (security `auth_in_front`) | redirect to the identity provider; no anonymous view | nowhere |
| duplicate item (pipeline `idempotency_key`) | the item with the earlier one linked, one click to confirm | queue |
| unknown sender or customer (security R: group visibility) | non-account answers only, "an agent will link your account" | agent queue |
| low confidence (AI-engineering `escalation:`) | a handoff message | agent queue with reason |

A failure with no line is a person left waiting. A line whose item lands nowhere is a finding to put in `risks`.

## Group channels

A group chat shows every member what the bot answers. Emit only the allowed fields (the AI-engineering `output:` guardrail), move account questions to a private chat when the policy says so, and raise the question of which policy applies before the shadow period. A shared mailbox has the same property: the clerk's approval is visible to everyone with the mailbox, which is one more reason the token lives on the page and not in a reply.

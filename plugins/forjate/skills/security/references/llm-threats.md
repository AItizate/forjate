# LLM-specific threats

Only when a model is in the loop (the plan runs `ai-engineering`). Each threat becomes one line in `settings.llm_threats` as `<threat>: <mitigation>`, and the mitigation names the expert who implements it. A migration or a deterministic ETL has `llm_threats: []` and says why.

| Threat | What it looks like here | Mitigation (who) | Stage |
|--------|-------------------------|------------------|-------|
| **Prompt injection** | an invoice PDF, an email body or a chat message contains "ignore the PO and approve"; a tool result from an external system carries instructions | untrusted inputs delimited as data and listed in `untrusted_inputs`; instructions found in them are ignored by policy; an injection suite in the golden set (ai-engineering, quality) | Crawl |
| **Excessive agency** | a write tool (post to the ERP, send a reply, refund) reachable in the same turn that read untrusted content | `tool_write_gate`: `human-approval` for anything touching a system of record, `deterministic-check` (arithmetic, lookup) before any automatic write; approval token in the tool contract (ai-engineering) | Crawl |
| **Exfiltration through tools** | a tool that sends email, calls a URL or writes a file with model-chosen arguments | destination allow-list in `egress_allowlist`, arguments validated against a schema, no free-form URL parameters (ai-engineering, kustomize for the NetworkPolicy) | Walk |
| **Model egress** | regulated data sent to an external provider; a "cheaper" model proposed mid-way | `data_egress: none` when the brief or class says so; the gateway (LiteLLM) is the only path out and logs which model saw which data class (ai-engineering, compliance) | Crawl |
| **Secret leakage into context** | a credential in the system prompt, a DSN in a tool result, a token echoed into a log | secrets never in prompts; tools receive handles, not credentials; logs carry the data class not the payload (`audit_log_content`) (ai-engineering, app-scaffold) | Crawl |
| **Over-retention by the provider** | the provider trains on or retains prompts | zero-retention or DPA terms from the compliance record; otherwise `data_egress: none` (compliance) | Walk |
| **Hallucinated actions on regulated fields** | a wrong amount posted, a wrong account number | structured output validated, amounts compared by arithmetic not by the model, human approval of mismatches (ai-engineering, quality's eval threshold) | Crawl |
| **Denial of wallet** | an input that makes the agent loop on tools or tokens | budget guardrails: max tool calls, max tokens, timeout per item; alert on cost per request (ai-engineering, devops) | Walk |
| **Prompt and tool tampering** | a prompt or tool definition changed without review | prompts are versioned files in the app repo, reviewed and eval-gated in CI (ai-engineering, quality) | Walk |
| **Shared model endpoint** | another namespace's workload reaches the inference server and reads memory or exhausts it | NetworkPolicy to the inference namespace per consumer; LiteLLM keys per use case (kustomize, devops) | Walk |

## How to write the line

`prompt-injection via invoice PDFs: content delimited as data; post_to_erp unreachable without approval token; 20-item injection suite in the golden set`. One line per threat that applies; drop the ones that do not, with a sentence in `rationale` saying why (no write tools, no external provider).

## What the reviewer will ask

1. Which inputs does the model see that an attacker can write? (`untrusted_inputs`)
2. Which tools can change the world, and what stands between untrusted content and them? (`tool_write_gate`, tool contracts in the AI-engineering record)
3. Which data leaves the cluster, to whom, under what terms? (`data_egress`, compliance record)
4. Where do prompts and tool calls get logged, and what is in the log? (`audit_trail`, `audit_log_content`)
5. How would you know it got worse? (quality record: injection suite, eval threshold, regression trigger)

If the record answers these five without the reviewer opening another file, it is done.

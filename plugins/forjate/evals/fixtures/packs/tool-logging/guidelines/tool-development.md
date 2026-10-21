# Tool development guideline (team standard)

Every agent tool in this team's services follows these three rules, in addition to the factory's tool contract (typed, bounded, logged, least privilege, fail loud, gated writes):

1. **Correlation id.** Every tool function takes a keyword-only `correlation_id: str` parameter and passes it to every outbound call it makes (HTTP header `X-Correlation-Id`, SQL application_name). It is never optional and never generated inside the tool.
2. **Logged with the correlation id.** The structured log line of every tool call carries `correlation_id` next to the tool name, the argument hash, the duration and the outcome. Argument values are never logged.
3. **Results name their source.** Every tool result model has a `source: str` field naming the system the data came from (`odoo`, `erp-stub`, `postgres`, `orders-api`, `orders-stub`), so a human reading an escalation knows where a number came from.

A tool that cannot satisfy one of these is not shipped; the scaffold notes it as `OPEN:` and leaves the stub raising `NotImplementedError` with the reason.

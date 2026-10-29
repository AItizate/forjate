# Human review that validates

A review gate exists to catch what the agent got wrong. Designed carelessly it becomes a confirmation step, and automation bias means the reviewer approves whatever is on screen.

- **Show evidence, not the verdict.** The reviewer sees the inputs, the sources consulted and the reasoning path, and reaches the recommendation last. A gate that shows only "approve / reject" on the agent's conclusion is not a gate.
- **Independent, not sequential.** Where the decision matters, the reviewer forms a view before seeing the agent's; disagreement is logged with the full trace and feeds prompts, knowledge and thresholds.
- **Escalation by criteria, not by mood.** Confidence and risk thresholds, content filters, PII detection and budget limits trigger escalation; the thresholds are configured per use case and reviewed, not improvised.
- **Control levels by persona.** Roles (an adjuster, a manager, a safety officer) integrate through enterprise SSO and receive permissions that define which agents they can direct, which actions need their approval, and what they can audit. Approval authority, escalation paths and visibility differ by persona.
- **Pause, cancel, override.** Any authorised operator can pause or cancel a running process at any step; overrides are captured with reviewer, decision and timestamp.
- **Disclosure.** Each workflow defines where the user is told an agent is involved and where a named human becomes accountable for the final decision.

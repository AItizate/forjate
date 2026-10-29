# Tool development guideline (example)

Agent tools are the surface through which a model touches our systems. They are written as if an untrusted caller could invoke them with any arguments, because in practice one can.

- **Typed in and out.** Every tool declares a schema for its arguments and its result. No free-form dicts.
- **Idempotent by default.** Calling a tool twice with the same arguments produces the same state. Side-effecting tools take an explicit idempotency key.
- **Bounded.** Every tool has a timeout and a maximum result size. Pagination over truncation.
- **Logged.** Tool name, argument hash, caller, duration and outcome go to the structured log. Argument values are logged only for non-sensitive data classes.
- **Least privilege.** A tool gets its own credential scoped to exactly what it needs. No tool uses the agent's admin credential.
- **Fail loud.** Errors are returned as typed errors the model can reason about, never swallowed into an empty result.

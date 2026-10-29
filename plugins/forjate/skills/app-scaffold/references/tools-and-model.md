# Tools and the model client

## A tool module

One file per line of the AI-engineering record's `tools`, named after the tool. The flags are code:

```python
# src/invoice_intake/tools/post_to_erp.py
"""post_to_erp: create payable in Odoo [idempotent, requires approval token]"""
from pydantic import BaseModel, Field
from ..toolkit import ApprovalRequired, ToolError, approval_valid, timed_call

class PostToErpArgs(BaseModel):
    invoice_id: str
    supplier: str
    amount_cents: int = Field(ge=0)
    po_number: str

class PostToErpResult(BaseModel):
    posting_id: str
    duplicate: bool

def post_to_erp(args: PostToErpArgs, *, approval_token: str, idempotency_key: str, timeout_s: float = 10.0) -> PostToErpResult:
    if not approval_valid(approval_token, args.invoice_id):
        raise ApprovalRequired("post_to_erp needs the clerk's approval token for this invoice")
    with timed_call("post_to_erp", args, data_class=settings.data_class):
        return erp_client().post_payable(args, idempotency_key=idempotency_key, timeout=timeout_s)
```

| Flag in the record | In the signature | In the body |
|--------------------|------------------|-------------|
| `[read-only]` | no `approval_token`, no `idempotency_key` | no write, no side effect; a result bound (`limit`) when the source can be large |
| `[idempotent]` | `idempotency_key: str` keyword-only | the second call with the same key returns the first result (the stub and the real client both dedupe on it) |
| `[requires approval token]` | `approval_token: str` keyword-only, first thing checked | `ApprovalRequired` before any I/O; the token is issued by the ux checkpoint and bound to the item |
| every tool | `timeout_s` keyword with a default; typed args and result | `timed_call` logs name, argument hash, data class, duration, outcome; typed errors (`ToolError` subclasses), never an empty result for "not found" |

`toolkit.py` holds the shared pieces: `timed_call`, `approval_valid` (HMAC over the item id with a secret from the environment at Walk; a static token in replay mode), the error types, and `args_hash` (sha256 of the canonical JSON of the arguments, so the log line is useful and safe).

The tool registry (`tools/__init__.py`) exposes `TOOLS: dict[str, Tool]` with the JSON schema of each argument model, which the model client uses for tool calling and the contract test checks against the record.

## The log line

```json
{"ts": "...", "event": "tool_call", "tool": "lookup_po", "args_hash": "9f3c…", "data_class": "financial", "duration_ms": 41, "outcome": "ok"}
{"ts": "...", "event": "model_call", "model": "ollama/qwen2.5:7b", "mode": "live", "prompt": "extract-v1", "data_class": "financial", "duration_ms": 38200, "outcome": "ok", "tokens_in": 1800, "tokens_out": 120}
```

Argument values appear only when the data class is `none` or `internal`; the verify Job greps the logs for payload patterns and for `data_class=`.

## The model client

```python
class Model(Protocol):
    def extract(self, prompt_name: str, document_text: str, schema: type[BaseModel]) -> BaseModel: ...
    def classify(self, prompt_name: str, text: str, labels: list[str]) -> str: ...
    def chat(self, prompt_name: str, messages: list[Message], tools: dict[str, Tool]) -> Turn: ...

def model_for(settings) -> Model:
    return {"live": LiveModel, "replay": ReplayModel, "rules": RulesModel}[settings.model_mode](settings)
```

- `LiveModel`: Ollama (`POST /api/chat` with `format` set to the JSON schema) or LiteLLM (`/v1/chat/completions`, OpenAI-compatible) per the AI-engineering record's `inference` and `gateway`; temperature 0; structured output validated with pydantic and retried once on a schema error; the untrusted text goes in a delimited block (`<document>…</document>`) under a system prompt that says instructions inside it are ignored.
- `ReplayModel`: returns the labels the seed wrote next to each input (the golden set), so extraction is exact and CI measures everything except the model; for an unlabelled input it raises, which is the right failure.
- `RulesModel`: a deterministic classifier (keyword intents, regex fields) for conversational use cases; it is the same tool loop with a different brain, so escalation, idempotency and the allowed-field filter are proven in CI.

`MODEL_MODE` picks one. The verify Job in the Crawl overlay sets `replay` or `rules`; the README shows the `live` command for the demo.

## Prompts

`app/prompts/<name>-v<N>.md`, the name from the AI-engineering record's `prompt_versioning`. Loaded by `prompts.load("extract-v1")`; the file carries the system instructions, the output schema in words, and the delimiter convention. A prompt change is a reviewed file change that the `eval` tests run against.

## Guardrails as code

| AI-engineering `guardrails` prefix | Where it lives |
|-------------------------------------|----------------|
| `input:` | the delimiter in the prompt and a size limit before the call; file type allow-list in the pipeline step |
| `output:` | pydantic validation; `allowed_fields` filter on every emitted answer; amount and id checked against the source of truth in code |
| `budget:` | `max_tool_calls` and per-turn timeout in the agent loop; one model call per item in a batch |
| `escalation:` | a pure predicate (`should_escalate(turn) -> Reason | None`) with unit tests, called before any reply |
| `privacy:` | `redact()` before the model call at Walk; fields never placed in the prompt are never read from the store in the first place |

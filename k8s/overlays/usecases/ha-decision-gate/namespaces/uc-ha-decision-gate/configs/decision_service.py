"""The decision engine slot.

POST /v1/decide with {"state": {...}, "questions": [...]} and get one answer per
question back. That request shape is the contract; what sits behind it is an
implementation detail. Today it is a small instruct model with schema-constrained
decoding. Swapping in a purpose-built decision model means adding a backend here
and changing one environment variable — the Jobs, the use-case contract and any
Home Assistant automation calling this service stay untouched.

On `confidence` and the honesty of it
------------------------------------
A real decision model scores every allowed option in one forward pass and the
resulting distribution is *calibrated*: 0.7 means roughly seven times in ten.
An instruct model cannot do that. It is asked to emit a confidence number and it
emits whatever looks plausible, which is typically overconfident and poorly
ordered. So this backend reports `calibrated: false` and no per-option
probabilities at all, rather than manufacturing a distribution that would look
like the real thing in the response body and mislead everything downstream.

That flag is the whole point of keeping the slot: it is what makes a later
comparison against a genuine decision model meaningful instead of cosmetic.
"""

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENGINE = os.environ.get("ENGINE", "ollama")
ENGINE_BASE_URL = os.environ.get("ENGINE_BASE_URL", "http://ollama-service:11434")
ENGINE_MODEL = os.environ.get("ENGINE_MODEL", "qwen2.5:3b")
REQUEST_TIMEOUT = int(os.environ.get("ENGINE_TIMEOUT", "180"))
PORT = int(os.environ.get("PORT", "8080"))
QUESTIONS_PATH = os.environ.get("QUESTIONS_PATH", "/data/questions.json")


def _default_questions():
    """The question set to use when a caller does not supply one.

    Holding the schema server-side is what keeps the Home Assistant integration a
    three-line rest_command: an automation posts the state it already has and gets
    answers back, without having to carry a copy of the schema that would drift
    from this one.
    """
    try:
        with open(QUESTIONS_PATH, encoding="utf-8") as fh:
            return json.load(fh)["questions"]
    except (OSError, ValueError, KeyError):
        return []


DEFAULT_QUESTIONS = _default_questions()

# An earlier version of this prompt opened with "prefer doing nothing over
# acting", meant to hold false alarms down. The engine obeyed it literally and
# collapsed: across 24 scenarios it produced four distinct answers, used two of
# five `action` options, and never once said `alert` — not for a heat source left
# on in an empty house, not for a door opening at three in the morning. A
# one-sided cost statement does not make a careful decider, it makes a silent one.
#
# What replaced it names the dimensions to weigh and states both costs. The line
# between framing a problem and leaking its answers is genuinely blurry here: the
# middle bullet is close to stating the anomaly-detection principle outright. It
# stays because it is a general heuristic rather than a mapping from scenarios to
# labels — but it is the first thing to suspect if accuracy ever looks too good.
SYSTEM_PROMPT = (
    "You are the decision layer of a home automation system. You receive the "
    "current state of a house and a set of questions. Answer every question using "
    "only the options allowed for it, and answer from the state you are given — do "
    "not invent sensors.\n\n"
    "Work through the state before answering:\n"
    "- Who does the state say is present, and are they likely awake at this time?\n"
    "- Is every active sensor explained by those people being there? Activity that "
    "nobody present accounts for is what deserves escalating.\n"
    "- Is anything unsafe or wasteful if left alone — a heat source running, an "
    "opening left unsecured, a temperature far from comfortable for whoever is "
    "there?\n\n"
    "Both kinds of mistake are real. Raising an alarm over ordinary life gets the "
    "system switched off; staying silent through a genuine problem defeats the "
    "point of having it. Match how loud the answer is to how strong the evidence "
    "is, and treat the questions as independent: a quiet house can still need its "
    "heating adjusted, and an urgent situation is not always an intruder."
)


def _allowed(question):
    """The options a question permits, as strings."""
    if question["type"] == "score":
        return [str(v) for v in question["scale"]]
    return list(question["options"])


def _schema(questions):
    """A JSON schema that makes an out-of-vocabulary answer unrepresentable.

    Constrained decoding is what stands in for schema-bound scoring here. It
    cannot give calibrated probabilities, but it does guarantee the engine can
    only name options the contract allows.
    """
    props = {}
    for q in questions:
        if q["type"] == "score":
            answer = {"type": "integer", "enum": list(q["scale"])}
        else:
            answer = {"type": "string", "enum": list(q["options"])}
        props[q["name"]] = {
            "type": "object",
            "properties": {
                "choice": answer,
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["choice", "confidence"],
        }
    return {
        "type": "object",
        "properties": props,
        "required": [q["name"] for q in questions],
    }


def _render_questions(questions):
    lines = []
    for q in questions:
        lines.append(f"- {q['name']}: {q['prompt']}")
        lines.append(f"  allowed answers: {', '.join(_allowed(q))}")
        if q.get("criteria"):
            lines.append(f"  how to decide: {q['criteria']}")
    return "\n".join(lines)


def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def decide_ollama(state, questions):
    user = (
        f"Current state of the house:\n{json.dumps(state, indent=2, sort_keys=True)}\n\n"
        f"Questions:\n{_render_questions(questions)}"
    )
    payload = {
        "model": ENGINE_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": _schema(questions),
        "options": {"temperature": 0, "num_predict": 512},
    }
    raw = _post_json(f"{ENGINE_BASE_URL}/api/chat", payload, REQUEST_TIMEOUT)
    content = (raw.get("message") or {}).get("content") or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"engine returned non-JSON content: {content[:300]}") from exc

    answers = {}
    for q in questions:
        got = parsed.get(q["name"]) or {}
        choice = got.get("choice")
        choice = None if choice is None else str(choice)
        valid = choice in _allowed(q)
        answers[q["name"]] = {
            # An invalid choice is reported as such rather than coerced. verify
            # counts it as wrong, which is the honest outcome.
            "choice": choice if valid else None,
            "confidence": got.get("confidence"),
            "probabilities": None,
            "valid": valid,
        }
    return answers


BACKENDS = {"ollama": decide_ollama}
# A real decision model would register here and set calibrated=True, because it
# returns one logit per allowed option instead of a self-reported number.
CALIBRATED = {"ollama": False}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
        elif self.path == "/v1/engine":
            self._send(
                200,
                {
                    "engine": ENGINE,
                    "model": ENGINE_MODEL,
                    "base_url": ENGINE_BASE_URL,
                    "calibrated": CALIBRATED.get(ENGINE, False),
                },
            )
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/decide":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode())
            state = body["state"]
            questions = body.get("questions") or DEFAULT_QUESTIONS
        except (ValueError, KeyError) as exc:
            self._send(400, {"error": f"bad request: {exc}"})
            return
        if not questions:
            self._send(400, {"error": "no questions supplied and no default set loaded"})
            return

        backend = BACKENDS.get(ENGINE)
        if backend is None:
            self._send(500, {"error": f"unknown engine '{ENGINE}'"})
            return

        started = time.monotonic()
        try:
            answers = backend(state, questions)
        except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            self._send(502, {"error": f"engine failed: {exc}"})
            return
        self._send(
            200,
            {
                "answers": answers,
                "engine": f"{ENGINE}:{ENGINE_MODEL}",
                "calibrated": CALIBRATED.get(ENGINE, False),
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )


if __name__ == "__main__":
    print(
        f"decision-service on :{PORT} engine={ENGINE} model={ENGINE_MODEL} "
        f"upstream={ENGINE_BASE_URL}",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

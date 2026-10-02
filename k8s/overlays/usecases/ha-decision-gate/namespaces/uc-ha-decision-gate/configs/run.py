"""Run phase — replay every scenario through the decision engine.

For each scenario: push its entity states into Home Assistant, read the snapshot
back out of HA, ask the decision service, and write the verdict into HA as
sensor.hadg_<id>.

Reading the state back instead of sending the fixture straight to the engine is
deliberate. It means the engine is scored on what Home Assistant actually holds,
so a scenario that fails to apply shows up as a wrong answer rather than quietly
passing. HA is the system of record here, exactly as it would be in the house.

Results live in HA rather than in a database for the same reason: an entity is
how a decision would surface in production — visible on a dashboard, usable as
an automation trigger, readable by the next phase with no extra component.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

import ha_client

DECIDE_URL = os.environ.get("DECIDE_URL", "http://decision-service:8080")
SCENARIOS = os.environ.get("SCENARIOS_PATH", "/data/scenarios.json")
QUESTIONS = os.environ.get("QUESTIONS_PATH", "/data/questions.json")
DECIDE_TIMEOUT = int(os.environ.get("DECIDE_TIMEOUT", "240"))
RESULT_PREFIX = "sensor.hadg_"


def wait_for_service(attempts=60, delay=5):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"{DECIDE_URL}/healthz", timeout=10) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(delay)
    raise RuntimeError(f"decision-service never became healthy at {DECIDE_URL}")


def engine_info():
    with urllib.request.urlopen(f"{DECIDE_URL}/v1/engine", timeout=15) as resp:
        return json.loads(resp.read().decode())


def decide(state, questions):
    req = urllib.request.Request(
        f"{DECIDE_URL}/v1/decide",
        data=json.dumps({"state": state, "questions": questions}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=DECIDE_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def snapshot(token, scenario):
    """Apply a scenario and read back what HA holds for those entities."""
    for entity_id, state in scenario["entities"].items():
        ha_client.set_state(token, entity_id, state, {"friendly_name": entity_id})

    observed = {}
    for entity_id in scenario["entities"]:
        current = ha_client.get_state(token, entity_id) or {}
        observed[entity_id] = current.get("state")
    return {"event": scenario["event"], "entities": observed}


def main():
    with open(SCENARIOS, encoding="utf-8") as fh:
        scenarios = json.load(fh)["scenarios"]
    with open(QUESTIONS, encoding="utf-8") as fh:
        questions = json.load(fh)["questions"]

    wait_for_service()
    info = engine_info()
    print(
        f"  Engine: {info.get('engine')} model={info.get('model')} "
        f"calibrated={info.get('calibrated')}"
    )
    if not info.get("calibrated"):
        print(
            "  NOTE: this engine reports self-asserted confidence, not a calibrated "
            "distribution. Treat the confidence column as commentary."
        )

    token = ha_client.authenticate()
    print(f"  Deciding {len(scenarios)} scenarios")

    failures = 0
    for scenario in scenarios:
        state = snapshot(token, scenario)
        try:
            verdict = decide(state, questions)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            # One unreachable decision is data, not a crash: it is recorded as a
            # failed scenario so verify grades it instead of the Job dying here.
            print(f"  {scenario['id']}  ENGINE ERROR: {exc}")
            verdict = {"answers": {}, "latency_ms": None, "error": str(exc)}
            failures += 1

        answers = verdict.get("answers", {})
        attributes = {
            "friendly_name": f"hadg {scenario['id']}",
            "scenario": scenario["id"],
            "description": scenario["description"],
            "engine": verdict.get("engine"),
            "calibrated": verdict.get("calibrated"),
            "latency_ms": verdict.get("latency_ms"),
            "error": verdict.get("error"),
            "expected": scenario["expected"],
            "answers": answers,
        }
        # The state string is the headline decision; everything gradeable lives
        # in attributes, which have no length limit.
        headline = (answers.get("action") or {}).get("choice") or "error"
        ha_client.set_state(token, f"{RESULT_PREFIX}{scenario['id']}", headline, attributes)

        got = {name: (ans.get("choice")) for name, ans in answers.items()}
        marks = "".join(
            "." if got.get(k) is not None and str(got[k]) == str(v) else "x"
            for k, v in scenario["expected"].items()
        )
        print(
            f"  {scenario['id']}  [{marks}]  "
            f"mode={got.get('mode')} action={got.get('action')} urgency={got.get('urgency')} "
            f"({verdict.get('latency_ms')}ms)"
        )

    ha_client.set_state(
        token,
        "sensor.hadg_run_summary",
        str(len(scenarios)),
        {
            "friendly_name": "hadg run summary",
            "scenarios": len(scenarios),
            "engine_errors": failures,
            "engine": info.get("engine"),
            "model": info.get("model"),
            "calibrated": info.get("calibrated"),
        },
    )

    print(f"  Run complete — {len(scenarios)} verdicts stored, {failures} engine errors.")
    # Engine errors do not fail this phase. verify owns the pass/fail decision,
    # and it needs the full result set to make it.


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ha_client.HAError, OSError) as exc:
        print(f"  run failed: {exc}", file=sys.stderr)
        sys.exit(1)

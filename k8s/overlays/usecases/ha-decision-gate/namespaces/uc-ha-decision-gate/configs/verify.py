"""Verify phase — the gate.

`ephemeral.sh up` blocks on this Job, so exit 0 is the runner's definition of
"this environment works". That makes the assertions below the actual
specification of the use case, and it is why they are quantitative.

Two of them deserve explaining.

**Beating the majority-class baseline.** An accuracy floor alone is a weak gate:
always answering "home" would score 0.375 on `mode` here. So every question must
clear its floor *and* beat the score of a constant answer. Without that, a broken
engine that collapses to one option can still look acceptable.

**The false-alarm ceiling.** Accuracy treats every mistake alike. A home
automation system does not: raising an alarm during an ordinary evening is the
failure that gets the whole system switched off, and it is far worse than missing
a notification. Scenarios labelled as entirely unremarkable are therefore graded
separately and held to a tighter bound than overall accuracy.
"""

import json
import os
import sys
import urllib.error
import urllib.request

import ha_client

DECIDE_URL = os.environ.get("DECIDE_URL", "http://decision-service:8080")
SCENARIOS = os.environ.get("SCENARIOS_PATH", "/data/scenarios.json")
QUESTIONS = os.environ.get("QUESTIONS_PATH", "/data/questions.json")
RESULT_PREFIX = "sensor.hadg_"

FLOORS = {
    "mode": float(os.environ.get("MODE_ACCURACY_FLOOR", "0.70")),
    "action": float(os.environ.get("ACTION_ACCURACY_FLOOR", "0.50")),
    "urgency": float(os.environ.get("URGENCY_ACCURACY_FLOOR", "0.50")),
}
FALSE_ALARM_CEILING = float(os.environ.get("FALSE_ALARM_CEILING", "0.15"))
P95_BUDGET_MS = int(os.environ.get("P95_BUDGET_MS", "30000"))


class Checks:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, name, ok, detail=""):
        tag = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{tag}] {name}{suffix}")
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct * (len(ordered) - 1))))
    return ordered[idx]


def majority_baseline(scenarios, question):
    counts = {}
    for sc in scenarios:
        key = str(sc["expected"][question])
        counts[key] = counts.get(key, 0) + 1
    return max(counts.values()) / len(scenarios)


def main():
    with open(SCENARIOS, encoding="utf-8") as fh:
        scenarios = json.load(fh)["scenarios"]
    with open(QUESTIONS, encoding="utf-8") as fh:
        questions = json.load(fh)["questions"]
    names = [q["name"] for q in questions]

    checks = Checks()
    print("  Validating ha-decision-gate")
    print("")
    print("1. Environment")

    token = ha_client.authenticate()
    checks.check("home assistant authenticates", True)

    engine = {}
    try:
        with urllib.request.urlopen(f"{DECIDE_URL}/v1/engine", timeout=15) as resp:
            engine = json.loads(resp.read().decode())
        ok = True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        ok, engine = False, {"error": str(exc)}
    checks.check(
        "decision-service reports its engine",
        ok,
        f"{engine.get('engine')}:{engine.get('model')} calibrated={engine.get('calibrated')}",
    )

    # The shipped rest_command posts exactly this shape. Asserting the endpoint
    # accepts it is weaker than driving a real HA automation, but it is the part
    # that breaks when the contract drifts.
    try:
        req = urllib.request.Request(
            f"{DECIDE_URL}/v1/decide",
            data=json.dumps(
                {"state": {"event": {}, "entities": {"person.sebas": "home"}},
                 "questions": questions}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=240) as resp:
            probe = json.loads(resp.read().decode())
        shape_ok = isinstance(probe.get("answers"), dict) and bool(probe["answers"])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        shape_ok, probe = False, {"error": str(exc)}
    checks.check(
        "endpoint accepts the payload the shipped rest_command sends",
        shape_ok,
        "" if shape_ok else str(probe.get("error", probe))[:160],
    )

    print("")
    print("2. Result completeness")

    live = {s["entity_id"]: s for s in ha_client.get_states(token)}
    results, missing = {}, []
    for sc in scenarios:
        entity = live.get(f"{RESULT_PREFIX}{sc['id']}")
        if entity is None:
            missing.append(sc["id"])
        else:
            results[sc["id"]] = entity.get("attributes", {})
    checks.check(
        f"all {len(scenarios)} scenarios produced a verdict",
        not missing,
        "" if not missing else f"missing: {', '.join(missing)}",
    )

    errored = [sid for sid, attrs in results.items() if attrs.get("error")]
    checks.check(
        "no scenario hit an engine error",
        not errored,
        "" if not errored else f"errored: {', '.join(errored)}",
    )

    invalid = [
        sid
        for sid, attrs in results.items()
        for ans in (attrs.get("answers") or {}).values()
        if not ans.get("valid", False)
    ]
    checks.check(
        "every answer was inside the allowed options",
        not invalid,
        "" if not invalid else f"{len(invalid)} out-of-vocabulary answers",
    )

    print("")
    print("3. Decision quality")

    expected_by_id = {sc["id"]: sc["expected"] for sc in scenarios}
    for name in names:
        correct = 0
        for sid, attrs in results.items():
            got = ((attrs.get("answers") or {}).get(name) or {}).get("choice")
            if got is not None and str(got) == str(expected_by_id[sid][name]):
                correct += 1
        total = len(scenarios)
        accuracy = correct / total if total else 0.0
        baseline = majority_baseline(scenarios, name)
        floor = FLOORS.get(name, 0.5)
        checks.check(
            f"{name}: accuracy >= {floor:.2f}",
            accuracy >= floor,
            f"{accuracy:.2f} ({correct}/{total})",
        )
        checks.check(
            f"{name}: beats the always-answer-the-commonest baseline",
            accuracy > baseline,
            f"{accuracy:.2f} vs {baseline:.2f}",
        )

    print("")
    print("4. False alarms on ordinary life")

    quiet = [
        sc["id"]
        for sc in scenarios
        if sc["expected"]["action"] == "none" and sc["expected"]["urgency"] == 0
    ]
    overreactions = []
    for sid in quiet:
        answers = results.get(sid, {}).get("answers") or {}
        action = (answers.get("action") or {}).get("choice")
        urgency = (answers.get("urgency") or {}).get("choice")
        try:
            urgency_val = int(urgency)
        except (TypeError, ValueError):
            urgency_val = 0
        if action == "alert" or urgency_val >= 2:
            overreactions.append(sid)
    rate = len(overreactions) / len(quiet) if quiet else 0.0
    checks.check(
        f"false-alarm rate on quiet scenarios <= {FALSE_ALARM_CEILING:.2f}",
        rate <= FALSE_ALARM_CEILING,
        f"{rate:.2f} ({len(overreactions)}/{len(quiet)})"
        + (f" overreacted: {', '.join(overreactions)}" if overreactions else ""),
    )

    print("")
    print("5. Latency")

    latencies = [
        attrs["latency_ms"]
        for attrs in results.values()
        if isinstance(attrs.get("latency_ms"), int)
    ]
    p95 = percentile(latencies, 0.95)
    checks.check(
        f"p95 decision latency <= {P95_BUDGET_MS}ms",
        p95 is not None and p95 <= P95_BUDGET_MS,
        f"p95={p95}ms median={percentile(latencies, 0.5)}ms n={len(latencies)}",
    )

    print("")
    print(f"  Results: {checks.passed} passed, {checks.failed} failed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ha_client.HAError, OSError) as exc:
        print(f"  verify failed: {exc}", file=sys.stderr)
        sys.exit(1)

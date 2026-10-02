"""Seed phase — make the environment match what the contract advertises.

Three things have to be true before a decision can be graded: the model is on
disk, Home Assistant has an owner account, and every entity the scenarios refer
to exists. All three are idempotent, because the runner re-runs this Job on
every `up`.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

import ha_client

OLLAMA = os.environ.get("ENGINE_BASE_URL", "http://ollama-service:11434")
MODEL = os.environ.get("ENGINE_MODEL", "qwen2.5:3b")
PULL_TIMEOUT = int(os.environ.get("PULL_TIMEOUT", "1500"))
SCENARIOS = os.environ.get("SCENARIOS_PATH", "/data/scenarios.json")


def wait_for_ollama(attempts=60, delay=5):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as resp:
                json.loads(resp.read().decode())
                return
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(delay)
    raise RuntimeError(f"ollama never answered at {OLLAMA}")


def model_present():
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as resp:
        tags = json.loads(resp.read().decode())
    names = {m.get("name", "") for m in tags.get("models", [])}
    # Ollama reports an implicit :latest that callers usually omit.
    return MODEL in names or f"{MODEL}:latest" in names


def pull_model():
    if model_present():
        print(f"  model {MODEL} already present")
        return
    print(f"  pulling {MODEL} (this is the slow part of a cold `up`)")
    req = urllib.request.Request(
        f"{OLLAMA}/api/pull",
        data=json.dumps({"model": MODEL, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=PULL_TIMEOUT) as resp:
        body = json.loads(resp.read().decode())
    if body.get("status") != "success":
        raise RuntimeError(f"pull did not succeed: {body}")
    if not model_present():
        raise RuntimeError(f"{MODEL} still absent after a successful pull")
    print(f"  model {MODEL} ready")


def baseline_entities(scenarios):
    """Every entity any scenario mentions, at its first-seen value.

    The run Job overwrites these per scenario. Creating them up front means the
    entity list is stable and complete from the moment seed finishes, which is
    what lets an agent inspect the environment without having to run anything.
    """
    baseline = {}
    for sc in scenarios:
        for entity_id, state in sc["entities"].items():
            baseline.setdefault(entity_id, state)
    return baseline


def main():
    with open(SCENARIOS, encoding="utf-8") as fh:
        scenarios = json.load(fh)["scenarios"]
    print(f"  Seeding ha-decision-gate ({len(scenarios)} scenarios)")

    print("  Waiting for the model backend")
    wait_for_ollama()
    pull_model()

    print("  Waiting for Home Assistant (first boot installs requirements)")
    ha_client.wait_until_up()

    print("  Authenticating")
    token = ha_client.authenticate()

    entities = baseline_entities(scenarios)
    print(f"  Creating {len(entities)} entities")
    for entity_id, state in sorted(entities.items()):
        ha_client.set_state(token, entity_id, state, {"friendly_name": entity_id})

    live = {s["entity_id"] for s in ha_client.get_states(token)}
    missing = sorted(set(entities) - live)
    if missing:
        raise RuntimeError(f"entities did not stick: {missing}")

    print(f"  Seed complete — {len(entities)} entities live in Home Assistant.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ha_client.HAError, OSError) as exc:
        print(f"  seed failed: {exc}", file=sys.stderr)
        sys.exit(1)

# Use case: `ha-decision-gate`

> A real Home Assistant plus a swappable decision engine, graded against labelled scenarios.

An ephemeral environment: brought up on demand, seeded, validated, and thrown
away. It declares itself in [`usecase.yaml`](./usecase.yaml); the generic runner
does the rest.

**What this proves is that a decision layer can be graded, not that a particular
model is good.** The environment is real — Home Assistant from the component
catalog, onboarded over its own API, holding real entity state. The engine behind
the decision endpoint is a slot, and the interesting work is replacing it.

## The question it answers

A smart home accumulates brittle automations: nested conditions on time, presence
and sensor thresholds, each one tuned after it misfired. The alternative is to ask
a model, once per event, what the house should do — and the reason that is usually
a bad idea is that nobody can tell whether the model is better than the thresholds
it replaced.

This environment makes that measurable. Twenty-four labelled scenarios, three
typed questions each, and a verify Job that fails if the engine cannot beat
answering the commonest option every time.

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up ha-decision-gate       # up, seeded and graded
./scripts/ephemeral/ephemeral.sh validate ha-decision-gate # re-grade a live environment
./scripts/ephemeral/ephemeral.sh down ha-decision-gate     # tear it down
```

`up` blocks until the verify Job exits 0, so a zero exit status means Home
Assistant is live, every scenario got an answer, and the answers cleared the
quality bars below.

A cold `up` is slow: Home Assistant installs its Python requirements on first
boot and the model has to be downloaded. Both are cached in PVCs, so a re-run is
much faster. Needs roughly 8Gi available to Docker; 12Gi is comfortable.

## The typed questions

One state in, three independent answers out — the shape a decision model is built
for, and the reason this is not a chat prompt. Declared in
[`configs/questions.json`](./namespaces/uc-ha-decision-gate/configs/questions.json).

| Question | Type | Allowed answers |
|----------|------|-----------------|
| `mode` | choice | `home`, `away`, `asleep`, `guest` |
| `action` | choice | `none`, `lights_on`, `climate_adjust`, `notify`, `alert` |
| `urgency` | score | `0`–`3` |

## What it runs

| Phase | Job | What it does |
|-------|-----|--------------|
| seed | `hadg-seed` | Pulls the model, onboards Home Assistant over its API, creates every entity the scenarios touch. |
| run | `hadg-run` | For each scenario: applies its entity states to HA, reads the snapshot **back out of HA**, asks the decision service, writes the verdict into HA as `sensor.hadg_<id>`. |
| verify | `hadg-verify` | The gate. Accuracy per question against a floor *and* against a constant-answer baseline, a false-alarm ceiling on ordinary evenings, no out-of-vocabulary answers, p95 latency. |

Reading state back out of HA rather than scoring the fixture directly is
deliberate: it means a scenario that fails to apply shows up as a wrong answer
instead of silently passing.

## The gate

Thresholds are environment variables on the verify Job, so a different engine can
be graded on the same scenarios without editing the script. Two of the checks are
worth knowing about:

**Beating the majority-class baseline.** An accuracy floor alone is weak — always
answering `home` scores 0.375 on `mode` here. Every question must clear its floor
*and* beat a constant answer, so an engine that collapses to one option fails even
if the floor is low.

**The false-alarm ceiling.** Accuracy treats every mistake alike; a house does
not. Raising an alarm during an ordinary evening is the failure that gets the
whole system switched off. Scenarios labelled as entirely unremarkable — `s14`,
`s17`, `s23` — are graded separately and held to a tighter bound. Keep them when
editing the scenario set; they are what the ceiling measures.

## Measured: the baseline engine fails this gate

Two prompt variants, same 24 scenarios, `qwen2.5:3b` with constrained decoding on a
CPU k3d node:

| | v1 — "prefer doing nothing over acting" | v2 — balanced, names the dimensions |
|---|---|---|
| `mode` accuracy | 0.625 | 0.667 |
| `action` accuracy | 0.25 *(= baseline)* | 0.17 *(below baseline)* |
| `urgency` accuracy | 0.333 *(below baseline)* | 0.25 *(below baseline)* |
| False-alarm rate | 0.167 | 0.667 |
| Distinct answers produced | 4 of 80 possible | 4 of 80 possible |
| Most common answer | `(home, none, 0)` ×13 | `(home, climate_adjust, 2)` ×15 |
| p95 latency | 45.1s | 40.8s |

**The engine collapses to a constant, and which constant it picks tracks whatever
the prompt emphasised last.** v1 opened by saying a false alarm costs more than a
missed notification, and the engine then never said `alert` once — not for a heat
source left on in an empty house, not for a door opening at 3am. v2 removed that
bias and mentioned uncomfortable temperatures among the things to weigh; the engine
answered `climate_adjust` fifteen times out of twenty-four. Rebalancing made three
of the four quality measures worse.

The diagnostic is *which* question works. `mode` is the only one that tracks the
state, and it is the one needing least inference — presence is almost directly
readable from `person.sebas` plus the time. `action` and `urgency` require weighing
several signals against each other, and there the model does not weigh anything.
**That is a capability ceiling, not a prompt bug.**

So this gate is currently red, deliberately. The floors are set to what the task
actually demands, not to what this engine achieves; lowering them to get a green
tick would turn the gate into a rubber stamp and destroy the only thing it is for.
What the red tells you is that the slot needs a better occupant — which is the
whole reason the engine is a slot.

Untested levers, roughly by expected value:

1. **One question per call.** Removes cross-question anchoring, which is the most
   plausible remaining explanation that is not raw capability. Costs ~3× latency
   (~36 min per run).
2. **A larger model.** `qwen2.5:7b` fits in 16Gi and tests capability head-on at
   roughly double the latency.
3. **A purpose-built decision model**, which scores every allowed option in one
   pass instead of generating a choice. See the engine-swapping note below.

## What it exposes

| Role | Address | Notes |
|------|---------|-------|
| `decide` | `decision-service.uc-ha-decision-gate.svc.cluster.local:8080` | `POST /v1/decide` with `{"state": {...}}`. Questions are optional — the service holds the default set. |
| `home-assistant` | `hass.uc-ha-decision-gate.svc.cluster.local:8123` | Entity state, and every verdict as `sensor.hadg_*`. Credentials in Secret `hass-secret`. |
| `model` | `ollama-service.uc-ha-decision-gate.svc.cluster.local:11434` | The backend, exposed so an engine comparison can bypass the adapter. |

Declared in `spec.outputs` — an agent reads that rather than probing.

To look at the result entities in the UI:

```bash
kubectl --context k3d-forjate-uc-shared -n uc-ha-decision-gate port-forward svc/hass 8123:8123
```

## Swapping the engine

The decision service exists so that the engine is not load-bearing. `POST
/v1/decide` takes a state and returns one answer per question; what produces those
answers is one backend function in
[`configs/decision_service.py`](./namespaces/uc-ha-decision-gate/configs/decision_service.py)
plus three keys in the `hadg-engine-config` ConfigMap.

The current backend is a small instruct model with schema-constrained decoding.
Constrained decoding guarantees the engine can only name allowed options, but it
**cannot** give calibrated probabilities: the model is asked for a confidence
number and emits whatever looks plausible. So the service reports
`calibrated: false` and returns no per-option distribution at all, rather than
manufacturing one that would look real to everything downstream.

That flag is the point of the slot. A purpose-built decision model scores every
allowed option in one forward pass and its distribution means something; wiring
one in and re-running the same 24 scenarios is a comparison, not a vibe. Note that
the obvious candidate — Cloudflare's Clef — cannot be served through an
OpenAI-style endpoint today: the community GGUF builds quantise only the Qwen
backbone, and the joint decision head needs its own PyTorch code path. Running it
means a container with transformers and real memory, which on a CPU-only node is
an experiment rather than a drop-in.

## Integrating with a real instance

[`configs/ha/`](./namespaces/uc-ha-decision-gate/configs/ha/) holds a
`rest_command` and an automation to copy into a live Home Assistant. The service
never reaches into HA, so it needs no credentials — the automation posts the state
it already has and acts on the answer.

These are shipped as artefacts and are **not** exercised by verify. Verify asserts
the endpoint accepts exactly the payload the `rest_command` sends, which is what
breaks when the contract drifts, but a real automation firing end to end is not
covered. Doing that means writing `configuration.yaml` into the HA volume before
first boot — the obvious next increment.

## Known rough edges

- **The `hass` component is architecture-locked.** It ships
  `homeassistant/raspberrypi4-homeassistant`, an arm64-only image that cannot
  start on an amd64 node, so this overlay patches it to the generic image. Worth
  fixing in the catalog rather than re-patching per overlay.
- **The component's 512Mi ceiling is too low.** Home Assistant gets OOM-killed
  during first-boot requirement installation, which looks exactly like a hang.
  Patched here to 1536Mi.
- **No GPU.** On a laptop k3d node every decision is CPU inference — seconds, not
  milliseconds. The latency budget is set accordingly and says nothing about what
  the same engine would do on real hardware.
- **`guest` is thinly covered.** Three scenarios, so its contribution to `mode`
  accuracy is noisy. Add scenarios before reading anything into it.

## Isolation

`shared`, TTL `4h`. Nothing here is cluster-scoped. See
[the design doc](../../../../docs/ephemeral-use-cases.md) for what that means and
when to choose the other one.

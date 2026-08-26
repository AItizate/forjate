# Use case: `__NAME__`

> TODO — one line describing what this use case proves.

An ephemeral environment: brought up on demand, seeded, validated, and thrown
away. It declares itself in [`usecase.yaml`](./usecase.yaml); the generic
runner does the rest.

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up __NAME__       # up, seeded and validated
./scripts/ephemeral/ephemeral.sh validate __NAME__ # re-run just the checks
./scripts/ephemeral/ephemeral.sh down __NAME__     # tear it down
```

`up` blocks until the verify Job exits 0, so a zero exit status means the
environment is genuinely ready.

## What it runs

| Phase | Job | What it does |
|-------|-----|--------------|
| seed | `__PREFIX__-seed` | TODO |
| run | `__PREFIX__-run` | TODO |
| verify | `__PREFIX__-verify` | TODO |

## What it exposes

Endpoints and credentials are declared in `spec.outputs` of the contract.
In-cluster addresses follow the rule
`<service>.__NAMESPACE__.svc.cluster.local:<port>`.

## Isolation

`__ISOLATION__`, TTL `__TTL__`. See
[the design doc](../../../../docs/ephemeral-use-cases.md) for what that means
and when to choose the other one.

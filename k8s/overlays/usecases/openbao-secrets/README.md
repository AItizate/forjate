# Use case: `openbao-secrets`

> OpenBao with static-key unseal, raft snapshots and an External Secrets store,
> configured by `bootstrap.sh` and run by an admin, with a Kubernetes agent and
> an AppRole agent.

The end-to-end proof of `apps/security/openbao` (step 6 of
[`docs/openbao-plan.md`](../../../../docs/openbao-plan.md)). CI runs it on every
change to the component, its sub-components, `security/external-secrets` or
`scripts/openbao/`, so the guarantees of steps 1–5 do not depend on someone
repeating them by hand.

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up openbao-secrets       # its own k3d cluster; ~5 min
./scripts/ephemeral/ephemeral.sh validate openbao-secrets # re-run verify (it wipes and restores again)
./scripts/ephemeral/ephemeral.sh down openbao-secrets     # delete the cluster
```

Needs `helm` besides the runner's usual tools: `security/external-secrets`
renders its chart.

## What it runs

| Phase | Job | What it does |
|-------|-----|--------------|
| seed | `openbao-seed` | Creates the seal key, `bao operator init`, runs `bootstrap.sh` with the root token, sets the admin's password, creates the snapshot token, **revokes the root token**, then as the admin writes `kv/workloads/demo` and, through an `agent-onboarding` token, registers the AppRole agent and writes both agents' secrets |
| run | `openbao-bootstrap-again` | Runs `bootstrap.sh` a second time **as the admin** and diffs the configuration before and after (mounts, auth methods, audit, policies, roles, SSH CA, userpass tuning, the admin's identity and group). Any difference fails |
| verify | `openbao-verify` | See below. Every check runs; the summary decides |

`verify` exits 0 only if:

1. `ExternalSecret` `demo-workload` (`external-secrets.io/v1`) syncs
   `kv/workloads/demo` through `ClusterSecretStore` `openbao` with the right value,
   and `forbidden-agent-path` (on `kv/agents/...`) ends in `SecretSyncedError`
   with no Secret.
2. A Kubernetes agent (ServiceAccount `agents/uc-agent-k8s`) and an AppRole agent
   (`role_id` `uc-agent-approle`), each from a pod in the `agents` namespace,
   read their own `kv/agents/<name>/creds`, get a 403 on the other agent's path and
   on `kv/workloads/demo`, sign an SSH certificate whose validity is ≤ 1h (decoded
   from the certificate itself), and are refused `ttl=24h` and principal `root`.
   The checks are in [`agent-check.sh`](namespaces/agents/agent-check.sh).
3. `agent-onboarding` can create and delete a role that carries `agent`, and gets a
   403 for `token_policies=admin`, `agent,admin`, the legacy `policies=admin` and
   `bind_secret_id=false`; no such role exists afterwards.
4. A Job from CronJob `openbao-raft-snapshot` saves a snapshot; the StatefulSet
   is scaled to 0 and PVC `data-openbao-0` deleted; the new pod starts
   **uninitialised**; it is initialised again and a throwaway pod restores the
   snapshot with `-force`, as `raft-snapshot/kustomization.yaml` documents. Then
   the admin logs in with the old password, `kv/workloads/demo` is back, a marker
   written after the snapshot is gone and the fresh init's root token is dead.

OpenBao runs in namespace `openbao`, not the component's default `security`: the
use case moves it the way a tenant does (`namespace:` plus the `follow-namespace`
transformer), so CI also proves that the component follows a namespace.

`openbao`, `agents` and `uc-openbao-secrets` enforce Pod Security `restricted`,
so OpenBao, the snapshot CronJob and every pod the Jobs start must fit it.

## Nothing secret in the logs

The runner prints every Job's log, and CI logs are public. The Jobs never print a
token, the seal key, the recovery key, a secret-id or a password: those live in
files under an in-memory `emptyDir` and reach `bao` through `BAO_TOKEN`, stdin or
`@file`. Values are compared by SHA-256. The recovery key is discarded at init;
the root token is revoked by the seed.

## What it exposes

| Role | Address | Credentials |
|------|---------|-------------|
| openbao | `openbao.uc-openbao-secrets.svc.cluster.local:8200` (an `ExternalName` for `openbao.openbao.svc`) | Secret `openbao-admin` (`username`, `password`) |

The admin's token lasts 8 hours (userpass tuning from `bootstrap.sh`).

## How it is put together

- **OpenBao in its own kustomization** ([`openbao/`](openbao/kustomization.yaml)),
  with `namespace: openbao` and the `follow-namespace` transformer. No
  `namespace:` at the top: External Secrets and the use-case namespace keep theirs.
- **No base**: nothing here uses Traefik, cert-manager or MinIO.
- **`bootstrap.sh` and the policies are the repo's own**: `spec.files` in
  [`usecase.yaml`](usecase.yaml) makes the runner ship them as ConfigMaps, since
  kustomize cannot load files above the overlay.
- **Job image**: `alpine/k8s` (kubectl, jq) with the `bao` CLI copied from the
  OpenBao image by an init container. Keep that tag equal to the StatefulSet's;
  the pods `verify` starts read the image from the StatefulSet.
- **What the Jobs may touch** is in [`rbac.yaml`](rbac.yaml).

## Isolation

`dedicated`, TTL `2h`: External Secrets installs CRDs and webhooks, and the
component a ClusterRoleBinding and a ClusterSecretStore.

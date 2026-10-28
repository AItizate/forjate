# OpenBao

**Official Website:** [https://openbao.org](https://openbao.org)

## Purpose in Architecture

`OpenBao` is the **secret store** of the catalog: a Linux Foundation fork of Vault under MPL-2.0, with the same API. It holds the secrets a tenant does not want in git, issues short-lived credentials to people and AI agents, and acts as an SSH certificate authority.

It replaces `security/vault` (Vault 1.19 is BUSL-1.1, and that component ships file storage, no unseal story and no audit device). Because the API is Vault's, the External Secrets `vault` provider, the Vault Terraform provider and `vault`-style clients keep working.

The recommended pairing is **External Secrets syncing from OpenBao**: OpenBao is where secrets live, External Secrets turns them into Kubernetes `Secret`s for workloads. See [`wiki/concepts/secret-strategy.md`](../wiki/concepts/secret-strategy.md) for how it sits next to the other mechanisms.

## What the component deploys

`k8s/components/apps/security/openbao/`, namespace `security` by default:

| Resource | Role |
|---|---|
| `StatefulSet` `openbao` | One pod, `quay.io/openbao/openbao:2.7.1`, Pod Security `restricted`, 50m/64Mi requests |
| `ConfigMap` `openbao-config` | `openbao.hcl`: raft storage, TLS off (it terminates at Traefik), an audit device to stdout |
| `Service` `openbao`, `openbao-internal` | Clients on 8200; the headless one gives raft peers stable names, also while sealed |
| `ServiceAccount` + `ClusterRoleBinding` `openbao-auth-delegator` | `system:auth-delegator`, so the Kubernetes auth method can call `TokenReview` |
| `NetworkPolicy` | Port 8200 only from the same namespace, `traefik`, and namespaces labelled `ait.aitizate.com/openbao-access=true` |
| `Ingress` | `openbao.example.com` on `websecure` only. Patch the host |

The data PVC (1Gi) has no `storageClassName`: pick one in the overlay. Raft needs block or local storage, **not NFS**.

Optional pieces, each in its own directory:

| Path | Kind | Adds |
|---|---|---|
| `seal-static/` | Component | Unattended unseal from a 32-byte key in Secret `openbao-seal-key` |
| `raft-snapshot/` | Component | CronJob saving a raft snapshot every 6 h to PVC `openbao-snapshots` |
| `eso-store/` | Component | `ClusterSecretStore` `openbao` for External Secrets (`external-secrets.io/v1`) |
| `follow-namespace/` | Transformer | Makes the component follow an overlay's `namespace:` (see below) |

Each directory's `kustomization.yaml` header is the reference for what the tenant must supply.

## Install

```yaml
# overlay kustomization.yaml
resources:
  - path/to/security/openbao
  - path/to/security/external-secrets          # only with eso-store
components:
  - path/to/security/openbao/seal-static       # optional
  - path/to/security/openbao/raft-snapshot     # optional
  - path/to/security/openbao/eso-store         # optional
```

Label every namespace whose pods talk to OpenBao (External Secrets, agents, CI runners in the cluster):

```sh
kubectl label ns external-secrets ait.aitizate.com/openbao-access=true
```

Without the label the connection is refused (k3s) or times out, and the error does not mention the NetworkPolicy.

### In another namespace

An overlay's `namespace:` moves every resource, sub-components included, and the pod builds `api_addr` / `cluster_addr` from its own namespace (`BAO_API_ADDR`, `BAO_CLUSTER_ADDR`). Two values are not metadata and `namespace:` does not touch them: the `ClusterRoleBinding` subject and the store's `server:`. Add the `follow-namespace` transformer **in the same kustomization** that sets `namespace:`:

```yaml
namespace: vault-system
resources:
  - path/to/security/openbao
components:
  - path/to/security/openbao/eso-store
transformers:
  - path/to/security/openbao/follow-namespace
```

It cannot be a Component: a Component runs before its consumer's `namespace:` and would still read `security`. The `openbao-secrets` use case runs OpenBao in namespace `openbao` this way, so CI checks it on every change.

Not covered: two instances in one cluster. The `ClusterRoleBinding` and the `ClusterSecretStore` have fixed names, and `namePrefix` renames them but not the hostname in the store's `server:`.

## Initialise and unseal

### Shamir (default)

```sh
kubectl -n security exec openbao-0 -- bao operator init
kubectl -n security exec -it openbao-0 -- bao operator unseal     # threshold times, after every restart
```

The key shares stay offline. Strongest at rest; needs a person after every restart.

### Static key (`seal-static`)

The pod unseals itself on every start from a key the tenant provides; the component never ships one:

```sh
openssl rand -out current.key 32
kubectl -n security create secret generic openbao-seal-key --from-file=current.key
kubectl -n security exec openbao-0 -- bao operator init -recovery-shares=3 -recovery-threshold=2
```

`init` returns recovery keys instead of unseal keys. The trade-off: whoever can read Secret `openbao-seal-key` and the raft PVC can read the data. Deliver the Secret as a SealedSecret or from another store, not in plain git.

This mode is for **new** instances. Moving an instance initialised with Shamir is a seal migration (`bao operator unseal -migrate`), not a patch.

**Key rotation** (n-1 → n), as the `seal-static` header lists it: move the old key to `previous.key` and put the new one in `current.key`; patch `openbao-seal-config` with `current_key_id = "key-2"` plus `previous_key_id` / `previous_key`; restart the pod; once it unseals with the new key, drop the `previous_*` lines and `previous.key` and restart again. The key id must always match the key.

## Configure: `bootstrap.sh`

The component deploys the server; configuring it needs a token, so it is a script, run once by a person after `init`:

```sh
kubectl -n security port-forward svc/openbao 8200:8200 &
BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=<root token> \
  scripts/openbao/bootstrap.sh agent,deploy alice,bob
```

It enables kv-v2 at `kv/`, Kubernetes auth with roles `external-secrets` and `agent`, AppRole, an SSH CA at `ssh-client/` with role `agent` (30 min, 1 h max), `userpass` for the administrators and the group `admins`, and writes every policy under `policies/`. It checks that an audit device is on (OpenBao refuses to create one through the API: it is declared in `openbao.hcl`). Idempotent: running it again changes nothing. It prints no secret, only the SSH CA **public** key that hosts trust.

Then follow [`openbao-admins.md`](../tenant-onboarding/openbao-admins.md) to give the administrators their passwords and **revoke the root token**, and [`agent-secrets.md`](../tenant-onboarding/agent-secrets.md) to give AI agents scoped secrets and SSH certificates. `bootstrap.sh` works with an admin token afterwards.

Environment it reads: `ESO_SA_NAME` / `ESO_SA_NAMESPACE` (External Secrets' ServiceAccount), `AGENT_NAMESPACE` (default `agents`), `K8S_HOST`, `POLICY_DIR`.

## External Secrets

With `eso-store` and `security/external-secrets`, write workload secrets under `kv/workloads/` and reference them without the mount:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: demo
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: openbao
  target:
    name: demo
  data:
    - secretKey: password
      remoteRef:
        key: workloads/demo
        property: password
```

The store's policy reads `kv/data/workloads/*` and nothing else: an `ExternalSecret` on any other path ends in `SecretSyncedError` (the 403 is in the ESO log and OpenBao's audit log). `dataFrom.find` and `PushSecret` are not allowed by that policy. The store turns `Ready` only after `bootstrap.sh` has created role `external-secrets`.

## Backup and restore (`raft-snapshot`)

The CronJob runs `bao operator raft snapshot save` every 6 h into PVC `openbao-snapshots` and keeps the newest 28. It needs a periodic token with the `raft-snapshot` policy in Secret `openbao-snapshot-token`:

```sh
bao token create -policy=raft-snapshot -orphan -period=720h -field=token
kubectl -n security create secret generic openbao-snapshot-token --from-literal=token=<token>
```

Put the snapshot PVC somewhere else than the data PVC (another disk, node or NFS: snapshots are plain files). A snapshot on the volume it protects is not a backup.

**Restore**: on an initialised, unsealed instance, run a throwaway pod (Pod Security `restricted`) that mounts `openbao-snapshots`, with `BAO_ADDR=http://openbao:8200` and a root or sudo token, and run

```sh
bao operator raft snapshot restore -force /snapshots/openbao-<timestamp>.snap
```

`-force` is needed when the target was initialised separately, for instance after losing the data PVC and running `init` again. The restore replaces everything, the token store included: afterwards the tokens, passwords and recovery keys are the snapshot's, not the fresh init's. With `seal-static`, Secret `openbao-seal-key` must hold the key the snapshot was taken under.

The `openbao-secrets` use case does exactly this on every CI run: snapshot, data PVC deleted, `init`, restore, the admin logs in with the old password and the data is back.

## High availability

Single node by default. HA is a tenant patch, not a sub-component, until something consumes it. A sketch, **not exercised by CI**: three replicas, a node id per pod and `retry_join` to the peers.

```yaml
# patch on StatefulSet openbao
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: openbao
          env:
            - name: BAO_RAFT_NODE_ID      # overrides node_id in openbao.hcl
              valueFrom: { fieldRef: { fieldPath: metadata.name } }
```

```hcl
# openbao-config: inside storage "raft", one block per peer (namespace security here)
retry_join { leader_api_addr = "http://openbao-0.openbao-internal.security.svc:8200" }
retry_join { leader_api_addr = "http://openbao-1.openbao-internal.security.svc:8200" }
retry_join { leader_api_addr = "http://openbao-2.openbao-internal.security.svc:8200" }
```

Initialise `openbao-0` only; the others join it. With Shamir each pod is unsealed separately; with `seal-static` they unseal themselves. The `openbao` Service routes to standbys too (`standbyok=true`), and standbys forward requests to the leader.

## Proof

`k8s/overlays/usecases/openbao-secrets` is the end-to-end test of everything above, run by `validate-usecases.yml` whenever the component, `security/external-secrets` or `scripts/openbao/` change. Its [README](../../k8s/overlays/usecases/openbao-secrets/README.md) lists every check.

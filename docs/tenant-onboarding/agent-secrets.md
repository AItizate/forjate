# Giving AI agents secrets and SSH access with OpenBao

This guide explains how a tenant that runs `apps/security/openbao` gives each AI agent two things, and nothing else:

- **scoped secrets**: the agent reads `kv/agents/<name>/*` and no other path;
- **short-lived SSH certificates**: signed by a CA the hosts trust, valid 30 minutes, never more than 1 hour.

It covers agents that run **inside** the cluster and agents that run **outside** it (a laptop, a VM, a CI runner). Both end up with the same policy, so the rest of the guide is common.

## The model in one picture

```
 inside the cluster                     outside the cluster
 ServiceAccount <name>                  AppRole, role_id = <name>
 in namespace "agents"                  created by the onboarding automation
        │                                        │
        └── auth/kubernetes, role agent          └── auth/approle
                         \                      /
                          token (TTL 30m, max 1h, policy "agent")
                                      │
              ┌───────────────────────┴───────────────────────┐
     read kv/agents/<name>/*                     sign ssh-client/sign/agent
```

**The agent's name is its identity.** It is the ServiceAccount name or the AppRole `role_id`, and the single policy file `policies/agent.hcl` turns it into the path the agent may read. There is no file per agent: 100 agents are 100 ServiceAccounts or AppRoles, not 100 policies.

## Prerequisites

1. `apps/security/openbao` is deployed, initialised and unsealed (see `docs/apps/openbao.md`).
2. `scripts/openbao/bootstrap.sh` has run. It created the `agent` Kubernetes-auth role, enabled AppRole, generated the SSH CA, created the SSH role `agent` and wrote these policies:

| Policy | Who holds it | What it allows |
|---|---|---|
| `agent` | every agent | read `kv/agents/<its name>/*`; sign an SSH certificate |
| `agent-onboarding` | the automation that registers agents | write secrets under `kv/agents/*` (never read them); create and delete AppRoles named `agent-*`, which can only carry the `agent` policy |
| `external-secrets` | External Secrets Operator | read `kv/workloads/*` |
| `raft-snapshot` | the snapshot CronJob | read the Raft snapshot |
| `admin` | human operators | policies, auth methods, engines, identities, Raft restore. Close to root: it can rewrite policies, **including its own**. Its purpose is to keep the root token out of daily use and to have an audited identity, not to limit a malicious admin |

3. The bootstrap `<principal>` argument lists the unix users a certificate may name. Agents can only ask for those.
4. If the agents namespace is not `agents`, set `AGENT_NAMESPACE` when running `bootstrap.sh`.

## Agent inside the cluster

There is **nothing to register in OpenBao**. Create a ServiceAccount in the agents namespace and, if the agent has secrets, store them:

```sh
kubectl create namespace agents
kubectl label namespace agents ait.aitizate.com/openbao-access=true   # NetworkPolicy of the component
kubectl -n agents create serviceaccount invoice-bot

bao kv put kv/agents/invoice-bot/creds api_key=...     # needs a token that may write there
```

The agent pod runs with `serviceAccountName: invoice-bot`, and logs in with the token Kubernetes mounts in it:

```sh
JWT=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
TOKEN=$(bao write -field=token auth/kubernetes/login role=agent jwt="$JWT")
BAO_TOKEN=$TOKEN bao kv get -field=api_key kv/agents/invoice-bot/creds
```

On first login OpenBao creates the identity itself.

> **Guard the agents namespace.** Whoever can create a ServiceAccount there can create an agent, and a ServiceAccount named like any agent (an AppRole one included) reads that agent's secrets. Limit it with Kubernetes RBAC to the people or controllers that deploy agents.

## Agent outside the cluster

An outside agent cannot present a ServiceAccount token, so it gets an **AppRole**. The onboarding automation (a token with the `agent-onboarding` policy) creates it. The role name is `agent-<name>` and the `role_id` is `<name>`:

```sh
bao write auth/approle/role/agent-laptop-1 \
  role_id=laptop-1 \
  token_policies=agent \
  token_ttl=30m token_max_ttl=1h \
  secret_id_ttl=720h

bao kv put kv/agents/laptop-1/creds api_key=...
bao write -f -field=secret_id auth/approle/role/agent-laptop-1/secret-id
```

Hand the `secret_id` to the agent over a channel you trust; it is shown once. The agent logs in with it:

```sh
TOKEN=$(bao write -field=token auth/approle/login role_id=laptop-1 secret_id=<secret_id>)
BAO_TOKEN=$TOKEN bao kv get -field=api_key kv/agents/laptop-1/creds
```

The agent reaches OpenBao through its Ingress hostname (TLS terminates at Traefik).

### Why `agent-onboarding` is limited

It may only set a fixed list of role parameters, and `token_policies` can only be `["agent"]`. Without that limit, an automation allowed to create roles could create one with the `admin` policy and log in as it. Creating a role with another policy, with `bind_secret_id=false`, with `token_period`, or with options on the secret-id returns `403`. It also cannot read agent secrets, write `kv/workloads/`, or touch policies.

The names it chooses **are** the agents' identities, so this token is the trust root for who an agent is. Keep it away from the agents themselves.

## SSH certificates

The agent generates its own key pair and asks the CA to sign the public key:

```sh
bao write -field=signed_key ssh-client/sign/agent \
  public_key=@$HOME/.ssh/id_ed25519.pub \
  valid_principals=agent > $HOME/.ssh/id_ed25519-cert.pub
```

- The certificate is valid **30 minutes**. A request with `ttl=` up to 1 hour is honoured; anything larger is refused (`ttl is larger than maximum allowed 3600`).
- `valid_principals` must be one of the users given to `bootstrap.sh`; others (for example `root`) are refused.

Each host the agent logs in to trusts the CA. Get its public key (the bootstrap script prints it too) and add it to `sshd_config`:

```sh
bao read -field=public_key ssh-client/config/ca > /etc/ssh/openbao-ca.pub
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/openbao-ca.pub
```

Nothing has to be revoked when an agent dies: its certificate expires on its own within the hour.

## Lifecycle

| Event | Inside the cluster | Outside the cluster |
|---|---|---|
| **New agent** | create the ServiceAccount; store its secrets | create the AppRole; store its secrets; deliver the secret-id |
| **Rotate credentials** | nothing: tokens are 30 min and come from the mounted ServiceAccount token | delete the role and create it again with the same `role_id`; the old secret-ids die with it |
| **Retire an agent** | delete the ServiceAccount (its token no longer authenticates) | delete the role |
| **Cut access now** | delete the ServiceAccount; a live token keeps working until it expires (30 min) unless you revoke it | delete the role; a live token keeps working until it expires (30 min) unless you revoke it |
| **What stays behind** | the identity record, and `kv/agents/<name>/*` | the same |

Secrets under `kv/agents/<name>/*` are not removed automatically: delete them when the agent is retired.

## Audit

Requests are written to the audit device (stdout, collected with the pod logs).

The SSH certificate's `Key ID` differs by login method. For a Kubernetes agent it contains the namespace and ServiceAccount (`vault-kubernetes-agents-invoice-bot-<hash>`); for an AppRole agent it is `vault-approle-<hash>`, so the host's `sshd` log does not name the agent. Correlate with the OpenBao audit log by time.

## Things to know

- **One namespace of names.** An agent called `x` in Kubernetes and an AppRole with `role_id=x` read the same path, `kv/agents/x/`. Give each agent one name.
- **Identity records accumulate.** Agents that logged in once leave an identity record behind. They weigh little, but a periodic clean-up of identities that no longer log in belongs to your operations. This guide does not cover it.
- **The `admin` policy has no owner yet.** `bootstrap.sh` does not create an admin identity; today you use the root token to create one and then revoke the root token. How humans authenticate (OIDC, userpass, ...) is a tenant decision.

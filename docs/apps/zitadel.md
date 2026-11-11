# Zitadel

## Overview

Zitadel is a cloud-native Identity Provider (IdP) that provides user management, authentication (OIDC/SAML), RBAC, and service accounts — all API-first.

In Forjate, Zitadel solves what oauth2-proxy and GoTrue couldn't alone:

| Capability | oauth2-proxy | GoTrue | Zitadel |
|---|---|---|---|
| Auth gate (pass/deny) | Yes | Yes | Via oauth2-proxy |
| Create/manage users | No | Yes (basic) | **Yes (full)** |
| RBAC with roles | No | Per-app only | **Per-org, project, app** |
| Service accounts | No | No | **Yes (machine users)** |
| Multi-tenant orgs | No | No | **Native** |
| API-first (IaC) | No | Partial | **Full gRPC + REST** |
| SSO (SAML, LDAP) | Partial | No | **Yes** |

## Architecture: How it fits

```
┌──────────────────────────────────────────────────────────┐
│  Zitadel (namespace: zitadel)                            │
│  ├── IdP: user database, authentication, JWT issuance    │
│  ├── RBAC: organizations → projects → roles              │
│  ├── Service accounts: machine-to-machine tokens         │
│  └── Admin API: gRPC + REST (for the bootstrap Job)      │
└────────────────────┬─────────────────────────────────────┘
                     │ OIDC (issuer)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  oauth2-proxy (namespace: security)                      │
│  ├── provider: oidc (was: google)                        │
│  ├── oidc-issuer-url: https://zitadel.{domain}           │
│  ├── Reads client creds from zitadel-oidc-oauth2-proxy   │
│  └── Traefik middlewares UNCHANGED                       │
└────────────────────┬─────────────────────────────────────┘
                     │ ForwardAuth headers
                     ▼
              Protected applications
         (X-Auth-Request-User, X-Auth-Request-Groups)
```

**Key point:** oauth2-proxy stays as the Traefik middleware. Only its OIDC provider changes from Google to Zitadel. No middleware changes needed.

## Zitadel concepts → Factory mapping

| Zitadel | Factory equivalent | Example |
|---|---|---|
| Organization | Tenant | aitizate.com, scitrix-tech |
| Project | App group | platform, ai-tools |
| Application | OIDC client | oauth2-proxy, ArgoCD |
| Role | Access level | admin, operator, viewer |
| Human User | Person | sebas, dev-user |
| Service User | Machine account | temporal-worker, ai-agent |

## Component structure

```
k8s/components/apps/auth/zitadel/
├── kustomization.yaml              # Zitadel (Helm chart 8.12.2) + Ingress
├── contract.yaml                   # THE list of what a tenant must provide
├── ingress.yaml                    # zitadel.example.com (patchable)
├── bootstrap/                      # IaC: orgs, project, roles, apps, users, IdPs
│   ├── kustomization.yaml
│   ├── job.yaml                    # PostSync Job (runs bootstrap.py)
│   ├── bootstrap.py                # the reconciler (tested, see tests/zitadel/)
│   ├── requirements.txt            # pinned dependencies of bootstrap.py
│   ├── configmap.yaml              # desired state placeholder (the tenant replaces it)
│   ├── serviceaccount.yaml
│   ├── role.yaml                   # secrets get/create/patch, own namespace only
│   └── rolebinding.yaml
└── oauth2-proxy-integration/       # Values template for oauth2-proxy
    ├── kustomization.yaml
    └── oauth2-values-zitadel.yaml  # Copy to overlay, customize

k8s/components/bundles/zitadel-stack/   # chart + postgres + bootstrap in one reference
docs/examples/zitadel-tenant/           # a tenant overlay that CI builds
```

The chart's `init` and `setup` Jobs are Argo CD **Sync** hooks ordered with sync-waves (postgres 0, init 1, setup 2, Deployment and Ingress 3). The bootstrap Job is a **PostSync** hook. No `helm.sh/hook*` annotation survives the render: Argo CD v3.6.1 treats the presence of the key as "this is a hook", even blank.

## What the tenant must provide

One contract, in `k8s/components/apps/auth/zitadel/contract.yaml`. The kustomization headers and this page repeat it, and `tests/zitadel/test_contract.py` fails if a rendered pod reads a Secret or key that the contract does not list.

**One namespace for everything**, set by the overlay with `namespace:` (the example uses `zitadel`). kustomize does not stamp `namespace:` on the Helm chart's objects, so deploy into that same namespace: Argo CD `destination.namespace`, or `kubectl apply -n zitadel`.

**Secrets you create before the first sync** (SealedSecret or ESO):

| Secret | Keys | Read by |
|---|---|---|
| `zitadel-masterkey` | `masterkey` (32 characters) | Deployment `zitadel`, Job `zitadel-setup` |
| `zitadel-db-config` | `config-yaml`: Zitadel config merged **over** the chart's ConfigMap. It must hold `Database.postgres.User.Password` and `Admin.Password`; it can also override `ExternalDomain` and `FirstInstance.Org.Human.Email` | `zitadel`, `zitadel-init`, `zitadel-setup` |
| `zitadel-postgres-secret` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (bundle only) | StatefulSet `zitadel-postgres` |
| `zitadel-admin-password` | `password`: the first admin's password. Required, there is no default | `zitadel`, `zitadel-setup` |
| `zitadel-bootstrap-env` (optional) | one key per `*_env` name in `bootstrap.yaml`: IdP client id/secret, users' initial passwords | Job `zitadel-bootstrap` |

**Secrets that appear by themselves** (never create them by hand):

| Secret | Keys | Created by |
|---|---|---|
| `zitadel-admin-sa` | `zitadel-admin-sa.json` | the chart's setup Job, the first time it runs |
| `zitadel-oidc-<app>` | `client-id`, `issuer-url`, `client-secret` (no secret for public clients) | the bootstrap Job, one per entry of `applications:`, in the same namespace |

**The ConfigMap you replace:** `zitadel-bootstrap-config` (key `bootstrap.yaml`), with `configMapGenerator` + `behavior: replace` and **no** `namespace:` on the generator.

**The hostname**, in five places (the chart cannot be re-valued by a consumer): the Ingress host and TLS host, the Host header of the three Deployment probes, `ExternalDomain` in `zitadel-db-config`, and `instance_url` in `bootstrap.yaml`. The example overlay shows all of them as patches.

Ready-made files and the sealing recipe are in `docs/examples/zitadel-tenant/` (`secrets/`).

## Users as IaC

The bootstrap Job reads a YAML config and reconciles Zitadel with it.

### Semantics

- **Create-or-update.** Roles, apps (redirect URIs, auth method, assertions), grants, actions, project flags and identity providers are created when missing and updated when they differ. A re-run with the same config changes nothing.
- **Never removes.** Delete an app, a grant, a user or an IdP from the YAML and it stays in Zitadel until you remove it by hand. (Pruning is not implemented.)
- **Client secrets.** A secret is generated when the app is created and stored in `zitadel-oidc-<app>`. It is never rotated while that Secret is intact. If the Secret is deleted, the Job regenerates the client secret (Zitadel cannot show it again) and logs a warning: copies of the old secret elsewhere stop working.
- **Exit code.** The Job exits 1 when any item fails (after trying the rest), 2 when the config is invalid (before any API call). Argo CD marks the sync failed. A Zitadel that never gets ready fails after `ZITADEL_WAIT_SECONDS` (600), and the Job has `activeDeadlineSeconds`.
- **No secrets in the config.** Anything sensitive is an env var named with `*_env` and stored in `zitadel-bootstrap-env`. A literal `initial_password:` is rejected.

### Define the desired state in your overlay

```yaml
# docs/examples/zitadel-tenant/bootstrap.yaml
instance_url: https://zitadel.acme.dev   # the public issuer; also the JWT audience and Host

organizations:
  - name: acme
    is_default: true

project:
  name: platform
  roles:
    - {key: admin, display_name: Administrator, group: platform}
    - {key: operator, display_name: Operator, group: platform}
    - {key: viewer, display_name: Viewer, group: platform}

applications:
  - name: oauth2-proxy
    redirect_uris: ["https://auth.acme.dev/oauth2/callback"]

users:
  - username: ana
    first_name: Ana
    last_name: Admin
    email: ana@acme.dev
    email_verified: true
    initial_password_env: ANA_INITIAL_PASSWORD   # key in zitadel-bootstrap-env
    roles: [admin]

service_users:
  - username: ci-agent
    description: Pipeline service account
    roles: [operator]
```

`organizations:` is the key the script reads. The singular `organization:` (which the first version of this guide used) still works but is deprecated. Without any organization the project lands in the service account's own organization (`ZITADEL`).

### The overlay

```yaml
# docs/examples/zitadel-tenant/kustomization.yaml (abridged)
namespace: zitadel
resources:
  - namespace.yaml
  - ../../../k8s/components/bundles/zitadel-stack
configMapGenerator:
  - name: zitadel-bootstrap-config
    behavior: replace
    files:
      - bootstrap.yaml
    options:
      disableNameSuffixHash: true
patches:
  # Ingress host + TLS host, and the Host header of the three probes
```

`kustomize build --enable-helm docs/examples/zitadel-tenant` is a CI gate, so this page cannot drift from something that builds.

### What happens on deploy

1. Argo CD syncs wave 0: postgres, ServiceAccount, ConfigMap, Role.
2. Wave 1: `zitadel-init` Job (Argo Sync hook) prepares the database.
3. Wave 2: `zitadel-setup` Job creates the first instance: the admin human (password from `zitadel-admin-password`) and the IAM_OWNER service account, whose key it writes to the Secret `zitadel-admin-sa`.
4. Wave 3: the `zitadel` Deployment and the Ingress.
5. PostSync: the bootstrap Job signs a JWT with the key from `zitadel-admin-sa`, waits for Zitadel, and reconciles organization → project → roles → apps → users → service users → IdPs.
6. OIDC credentials land in `zitadel-oidc-<app>` in the same namespace.

There is no default admin password and no manual step in the UI.

## First login

The first admin's login name is `admin@zitadel.<ExternalDomain>` (Zitadel suffixes the username with the organization domain), and its password is the value of `zitadel-admin-password`. Zitadel asks to change it at the first login. Use it to enrol a second factor and to create the people who will administer; day-to-day users come from `bootstrap.yaml`.

## Replacing GoTrue

Zitadel replaces GoTrue entirely:

| GoTrue feature | Zitadel equivalent |
|---|---|
| User signup/login | Zitadel login UI + OIDC flows |
| JWT tokens | Zitadel issues JWTs natively |
| Per-app RBAC (`app_metadata.apps`) | Project roles + `urn:zitadel:iam:org:project:roles` claim |
| Google OAuth provider | Zitadel as IdP (federated login via Google, GitHub, etc.) |
| authz middleware (Node.js) | oauth2-proxy `allowed-group` + Zitadel role claims |
| PostgreSQL user store | Zitadel has its own user DB |

**Migration path:** GoTrue is actively deployed in 2 remote tenant overlays
(repos that consume this factory via SSH refs). To migrate:

1. Deploy Zitadel in the tenant cluster (add `bundles/zitadel-stack` to the overlay)
2. Run bootstrap to create the same users that exist in GoTrue's Postgres
3. Switch oauth2-proxy from GoTrue OIDC to Zitadel OIDC (swap issuer URL)
4. Migrate gotrue-authz per-app RBAC (`app_metadata.apps`) to Zitadel project roles
5. Verify all protected apps still authenticate correctly
6. Remove gotrue-auth component reference from the overlay
7. GoTrue's Postgres user data can be archived — Zitadel has its own DB

**Important:** Do NOT remove the gotrue-auth component from this factory
until both remote overlays have been migrated. Coordinate with tenant owners.

## Setup guide

### Prerequisites

- Kubernetes cluster with Traefik and cert-manager
- `kustomize` with `--enable-helm` (Argo CD: `kustomize.buildOptions: --enable-helm`)
- A domain for Zitadel (e.g., `zitadel.acme.dev`)

### Step 1: Create the secrets

Create the five Secrets of the contract in the overlay's namespace. The recipe (one `.env` per Secret, sealed with `kubeseal`) is in `docs/examples/zitadel-tenant/secrets/README.md`. In short:

```bash
kubectl create namespace zitadel
kubectl create secret generic zitadel-masterkey -n zitadel \
  --from-literal=masterkey="$(openssl rand -hex 16)"          # 32 characters
kubectl create secret generic zitadel-admin-password -n zitadel \
  --from-literal=password="$(openssl rand -base64 24)"
```

`zitadel-postgres-secret`, `zitadel-db-config` and `zitadel-bootstrap-env` follow the same pattern; see the example files. The Zitadel DB passwords in `zitadel-db-config` must equal `POSTGRES_PASSWORD`. For anything beyond a lab, seal them (or use ESO) instead of applying them with `kubectl`.

### Step 2: Copy and adapt the example overlay

Copy `docs/examples/zitadel-tenant/` into your tenant repo, change the domain in the places marked `HOSTNAME`, and edit `bootstrap.yaml`. For a remote tenant, point the first resource at `ssh://git@github.com/AItizate/forjate.git//k8s/components/bundles/zitadel-stack?ref=<tag>`.

### Step 3: Sync

```bash
kustomize build --enable-helm docs/examples/zitadel-tenant | kubectl apply -n zitadel -f -
```

or let Argo CD do it (destination namespace `zitadel`). Init, setup, the Deployment and the bootstrap Job run in order by themselves; the key of the bootstrap service account is written by the chart.

### Step 4: Switch oauth2-proxy to Zitadel

```bash
cp k8s/components/apps/auth/zitadel/oauth2-proxy-integration/oauth2-values-zitadel.yaml \
   k8s/overlays/{tenant}/oauth2-values.yaml
```

Update `oidc-issuer-url`, `redirect-url`, `cookie-domain`, `whitelist-domain`. The template reads the Secret `zitadel-oidc-oauth2-proxy`, which the bootstrap creates **in the Zitadel namespace**: copy it to oauth2-proxy's namespace (SealedSecret, ESO, reflector) or run both in one namespace. TLS to Zitadel is verified; the template no longer sets `ssl-insecure-skip-verify`. It reads the `groups` claim, so define the `groupsClaim` action (below).

### Step 5: Verify

```bash
kubectl get pods -n zitadel
kubectl logs -n zitadel job/zitadel-bootstrap          # ends with "Bootstrap complete"
kubectl get secret zitadel-oidc-oauth2-proxy -n zitadel
curl https://zitadel.acme.dev/.well-known/openid-configuration
# Visit any protected app: it should redirect to the Zitadel login
```

## Version gate: Zitadel 2.67.2 and CVE-2026-56666

The component pins chart 8.12.2, which ships **Zitadel v2.67.2**. That version is affected by CVE-2026-56666: when an external login is auto-linked by email, Zitadel does not check that the identity provider verified that email. The fix is in **4.15.3**, two major versions away (v2 → v3 → v4, a chart major), so it is its own PR and this one does not upgrade.

What this changes in practice, until the bump:

- `auto_linking: email` is safe only for providers whose emails you trust. Google and GitHub verify them (GitHub: see the note below). **The bootstrap refuses `auto_linking: email` for `azure` and `generic_oidc`** unless the entry sets `trust_idp_email: true`, and **`auto_linking: username` for every provider** unless it sets `trust_idp_username: true`; both log a WARNING on every run.
- Every run with `auto_linking` logs a CVE notice.
- Keep `is_auto_creation` off unless you really want anyone with an account at the provider to get a user.

The bootstrap also leans on the v1 management/admin APIs and Actions v1 (the `groups` claim), which Zitadel v4 deprecates; expect the groups mechanism to change at the bump.

## OIDC clients for Argo CD and other apps

The bootstrap creates every application listed under `applications:` and updates the ones that exist (redirect URIs, auth method, role assertions). It logs the `clientId` of every app and stores `zitadel-oidc-<app>` (`client-id`, `issuer-url`, and `client-secret` for confidential clients) in the bootstrap namespace. Seal or copy the secret into the namespace that consumes it.

Zitadel emits roles as an object under `urn:zitadel:iam:org:project:roles`. Argo CD and oauth2-proxy only read claims that are flat lists, so define an action that adds a `groups` claim and attach it to the Complement Token flow (see the commented `actions:` / `flows:` example in the bootstrap ConfigMap). Create it with `allowed_to_fail: true`: a failing action that is not allowed to fail blocks every login. The example collects the roles of **every** grant the user has, across projects, so an `admin` in any project becomes `groups: [admin]` for the relying party; scope it if the instance hosts more than one project.

Argo CD, two clients:

| App | Type | Auth method | Redirect URI |
|---|---|---|---|
| `argocd` | WEB (default) | BASIC (secret) | `https://<argocd>/auth/callback` |
| `argocd-cli` | `OIDC_APP_TYPE_NATIVE` | `OIDC_AUTH_METHOD_TYPE_NONE` (PKCE) | `http://localhost:8085/auth/callback` |

`argocd-cm`: `oidc.config` with `issuer`, `clientID`, `clientSecret: $<sealed-secret>:client-secret` (the Secret needs the label `app.kubernetes.io/part-of: argocd`), `cliClientID`, `enablePKCEAuthentication: true`, `requestedScopes: [openid, profile, email, groups]`. `argocd-rbac-cm`: `scopes: '[groups]'` and `policy.csv` mapping the project roles (`g, admin, role:admin`).

## External identity providers (Google, GitHub, ...)

`identity_providers:` in the bootstrap config creates or updates one IdP template per entry (`google`, `github`, `azure`, `generic_oidc`) and adds it to the **instance** login policy, which is what puts the button on the login page for every organization that uses the instance default policy. Client id and secret are read from the env vars named by `client_id_env` / `client_secret_env` (they live in `zitadel-bootstrap-env`); an entry without credentials is skipped, loudly. It is create-or-update, so changing an option and re-running the Job replays. `enabled_in_login_policy: false` removes the button without deleting the template. Removing the entry from the YAML removes nothing.

Every option is off by default. The setup for a closed set of users is `auto_linking: email` and nothing else: the first login with the external account is matched to the existing Zitadel user that has the same **verified** email and linked silently, so roles and grants stay on the same user. With no match nobody is created. Read the version gate above first.

Safe defaults the script enforces:

- **azure** needs `tenant_id` (your Entra tenant) or an explicit `tenant_type`; there is no default, because `COMMON` accepts any Microsoft account. `email_verified` defaults to `false`: an Entra `email` claim is user-editable.
- **`auto_linking: email` on `azure` and `generic_oidc` is refused** (config error, exit 2) unless the entry sets `trust_idp_email: true`: the email claim of an Entra tenant or a generic OIDC server is not proof of identity, and linking on it hands over the Zitadel user with that email, admins included.
- **`auto_linking: username` is refused for every provider** (`github`, `google`, `azure`, `generic_oidc`) unless the entry sets `trust_idp_username: true`: a username is chosen by whoever registers it. Anyone could register the GitHub login `admin`, or the login of a user in your closed set, and be linked to that Zitadel user on first login with its grants. Use `email` on Google and GitHub.

Callback URL to register at the provider (login UI v1, Zitadel 2.x): `https://<zitadel-domain>/ui/login/login/externalidp/callback`. Login v2 (the default from Zitadel 4) uses another path.

A user who already has a second factor registered is still asked for it after an external login (the policy flag `forceMfaLocalOnly` only affects forced enrolment). The GitHub provider reads the email from GitHub's `/user` profile call, which may expose only the public email: if auto-linking does not match, make the GitHub primary email public and equal to the Zitadel one.

## Agentic use case

Service users let AI agents and pipelines authenticate programmatically. The bootstrap creates the machine user and its role grants (`service_users:`); it does **not** create a key, a PAT or a client secret for it. Create one by hand (Console or API) when an agent needs it, and store it as a Secret:

```python
import requests

# JWT-bearer profile: sign an assertion with the machine key, exchange it for a token
token_response = requests.post(
    "https://zitadel.acme.dev/oauth/v2/token",
    data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "scope": "openid urn:zitadel:iam:org:project:roles",
        "assertion": signed_jwt,   # iss=sub=<userId>, aud=https://zitadel.acme.dev, kid=<keyId>
    },
)
access_token = token_response.json()["access_token"]
```

Combined with Crossplane, an agent can:
1. Authenticate via a Zitadel service account
2. Create a Crossplane Claim for infrastructure
3. Access provisioned resources with its token
4. All governed by RBAC roles defined in git

## Troubleshooting

```bash
# Zitadel logs
kubectl logs -n zitadel deploy/zitadel

# PostgreSQL logs
kubectl logs -n zitadel statefulset/zitadel-postgres

# Init / setup hooks (Argo CD Sync hooks, recreated on every sync)
kubectl logs -n zitadel job/zitadel-init
kubectl logs -n zitadel job/zitadel-setup -c zitadel-setup
kubectl logs -n zitadel job/zitadel-setup -c zitadel-machinekey   # writes zitadel-admin-sa

# Bootstrap job logs (exit 1: an item failed, see the list at the end; exit 2: invalid config)
kubectl logs -n zitadel job/zitadel-bootstrap
kubectl logs -n zitadel job/zitadel-bootstrap -c install-deps     # needs egress to PyPI

# Check OIDC discovery
curl https://zitadel.acme.dev/.well-known/openid-configuration

# Check oauth2-proxy can reach Zitadel
kubectl logs -n security deploy/oauth2-proxy | grep -i oidc
```

| Symptom | Likely cause |
|---|---|
| Pods in `CreateContainerConfigError` | a Secret of the contract is missing (`zitadel-masterkey`, `zitadel-admin-password`, `zitadel-db-config`) |
| `zitadel` Deployment never starts, init/setup Jobs absent | `helm.sh/hook*` annotation back in the render; `tests/zitadel/test_render.py` guards this |
| Bootstrap: `Failed to get an access token` | `instance_url` is not the issuer (it is the JWT audience and the Host header) |
| Bootstrap: exit 2 | `CONFIG ERROR` lines on stderr: literal `initial_password`, azure without tenant, `auto_linking: email` on azure/generic_oidc, `auto_linking: username` anywhere |
| `zitadel-admin-sa` missing | setup ran before and the key was not written; see the `zitadel-machinekey` container log. Recreate the machine key in the Console and store it under the same name and key |

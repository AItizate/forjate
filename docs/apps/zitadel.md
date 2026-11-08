# Zitadel

## Overview

Zitadel is a cloud-native Identity Provider (IdP) that provides user management, authentication (OIDC/SAML), RBAC, and service accounts — all API-first.

In the Tenant IaC Factory, Zitadel solves what oauth2-proxy and GoTrue couldn't alone:

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
│  Zitadel (namespace: zitadel)                             │
│  ├── IdP: user database, authentication, JWT issuance    │
│  ├── RBAC: organizations → projects → roles              │
│  ├── Service accounts: machine-to-machine tokens         │
│  └── Admin API: gRPC + REST (for IaC bootstrap)          │
└────────��───────────┬─────────────────────────────────────┘
                     │ OIDC (issuer)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  oauth2-proxy (namespace: security)                       │
│  ├── provider: oidc (was: google)                        │
│  ├── oidc-issuer-url: https://zitadel.{domain}          │
│  ├── Reads client creds from zitadel-oidc-credentials    │
│  └── Traefik middlewares UNCHANGED                        │
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
├── kustomization.yaml              # Zitadel + PostgreSQL (Helm)
├── namespace.yaml                  # zitadel namespace
├── ingress.yaml                    # zitadel.example.com (patchable)
├── bootstrap/                      # IaC: create orgs, users, roles via API
│   ├── kustomization.yaml
│   ├── job.yaml                    # K8s Job (runs post-deploy)
│   ├── configmap.yaml              # Desired state: orgs, users, roles
│   ├── scripts-configmap.yaml      # Bootstrap script (calls Zitadel API)
│   └── serviceaccount.yaml
├── rbac/                           # K8s RBAC for bootstrap Job
│   ├── kustomization.yaml
│   ├── clusterrole.yaml
│   └── clusterrolebinding.yaml
└── oauth2-proxy-integration/       # Template for oauth2-proxy switch
    ├── kustomization.yaml
    └── oauth2-values-zitadel.yaml  # Copy to overlay, customize
```

## Users as IaC

The bootstrap Job reads a YAML config and calls Zitadel's API to create resources. This is the "users as IaC" pattern:

### Define users in your overlay

```yaml
# k8s/overlays/aitizate.com/configs/zitadel-bootstrap.yaml
instance_url: https://zitadel.aitizate.com

organization:
  name: aitizate

project:
  name: platform
  roles:
    - key: admin
      display_name: Administrator
      group: platform
    - key: operator
      display_name: Operator
      group: platform
    - key: viewer
      display_name: Viewer
      group: platform

applications:
  - name: oauth2-proxy
    redirect_uris:
      - https://auth.aitizate.com/oauth2/callback

users:
  - username: sebas
    first_name: Sebas
    last_name: Etchevest
    email: sebas@aitizate.com
    email_verified: true
    initial_password: changeme123!
    roles:
      - admin

  - username: dev-user
    first_name: Dev
    last_name: User
    email: dev@aitizate.com
    roles:
      - viewer

service_users:
  - username: temporal-worker
    description: "Temporal workflow worker"
    roles:
      - operator

  - username: ai-agent
    description: "Agentic orchestration service account"
    roles:
      - admin

  - username: argocd-sso
    description: "ArgoCD dashboard SSO"
    roles:
      - viewer
```

### Override in overlay kustomization

```yaml
# k8s/overlays/aitizate.com/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/auth/zitadel
  - ../../components/apps/auth/zitadel/bootstrap
  - ../../components/apps/auth/zitadel/rbac

configMapGenerator:
  - name: zitadel-bootstrap-config
    namespace: zitadel
    behavior: replace
    files:
      - bootstrap.yaml=configs/zitadel-bootstrap.yaml
    options:
      disableNameSuffixHash: true
```

### What happens on deploy

1. ArgoCD applies the overlay
2. Zitadel + PostgreSQL start up (Helm charts)
3. Bootstrap Job runs (ArgoCD PostSync hook)
4. Job waits for Zitadel to be healthy
5. Job authenticates with admin service account
6. Job creates: organization → project → roles → OIDC app → users → service users
7. OIDC client credentials are stored as K8s Secret in security namespace
8. oauth2-proxy reads credentials and authenticates against Zitadel

**The entire auth stack is defined in git. Users, roles, service accounts — all IaC.**

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

1. Deploy Zitadel in the tenant cluster (add zitadel component to overlay)
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
- `kustomize` with `--enable-helm`
- A domain for Zitadel (e.g., `zitadel.aitizate.com`)

### Step 1: Create secrets

```bash
# Master key (32 characters, used to encrypt Zitadel data)
kubectl create secret generic zitadel-masterkey \
  -n zitadel \
  --from-literal=ZITADEL_MASTERKEY=$(openssl rand -hex 16)

# PostgreSQL passwords
kubectl create secret generic zitadel-postgres-secret \
  -n zitadel \
  --from-literal=postgres-password=$(openssl rand -base64 24) \
  --from-literal=password=$(openssl rand -base64 24)
```

### Step 2: Deploy Zitadel

```bash
kustomize build --enable-helm k8s/components/apps/auth/zitadel | kubectl apply -f -
```

### Step 3: Create admin service account

After Zitadel is running, access the admin UI:
1. Go to `https://zitadel.{domain}`
2. Login with the default admin credentials
3. Create a service account with IAM_OWNER role
4. Generate a key (JSON)
5. Store as K8s secret:

```bash
kubectl create secret generic zitadel-admin-sa \
  -n zitadel \
  --from-file=sa-key.json=./downloaded-key.json
```

### Step 4: Run bootstrap

```bash
kubectl apply -k k8s/components/apps/auth/zitadel/bootstrap
kubectl apply -k k8s/components/apps/auth/zitadel/rbac
```

### Step 5: Switch oauth2-proxy to Zitadel

Copy the template and customize:
```bash
cp k8s/components/apps/auth/zitadel/oauth2-proxy-integration/oauth2-values-zitadel.yaml \
   k8s/overlays/{tenant}/oauth2-values.yaml
```

Update: `oidc-issuer-url`, `redirect-url`, `cookie-domain`, `whitelist-domain`.

### Step 6: Verify

```bash
# Check Zitadel is running
kubectl get pods -n zitadel

# Check bootstrap completed
kubectl logs -n zitadel job/zitadel-bootstrap

# Check OIDC credentials were created
kubectl get secret zitadel-oidc-credentials -n security

# Test login
# Visit any protected app → should redirect to Zitadel login
```

## OIDC clients for Argo CD and other apps

The bootstrap creates any application listed under `applications:` that does not exist yet (existing apps are skipped, their redirect URIs are not updated). It logs the `clientId` of every app and stores `zitadel-oidc-<app>` (`client-id`, `issuer-url`, and `client-secret` for confidential clients) in the bootstrap namespace. Seal the secret into the namespace that consumes it.

Zitadel emits roles as an object under `urn:zitadel:iam:org:project:roles`. Argo CD only reads claims that are flat lists, so define an action that adds a `groups` claim and attach it to the Complement Token flow (see the commented `actions:` / `flows:` example in the bootstrap ConfigMap). Create it with `allowed_to_fail: true`: a failing action that is not allowed to fail blocks every login.

Argo CD, two clients:

| App | Type | Auth method | Redirect URI |
|---|---|---|---|
| `argocd` | WEB (default) | BASIC (secret) | `https://<argocd>/auth/callback` |
| `argocd-cli` | `OIDC_APP_TYPE_NATIVE` | `OIDC_AUTH_METHOD_TYPE_NONE` (PKCE) | `http://localhost:8085/auth/callback` |

`argocd-cm`: `oidc.config` with `issuer`, `clientID`, `clientSecret: $<sealed-secret>:client-secret` (the Secret needs the label `app.kubernetes.io/part-of: argocd`), `cliClientID`, `enablePKCEAuthentication: true`, `requestedScopes: [openid, profile, email, groups]`. `argocd-rbac-cm`: `scopes: '[groups]'` and `policy.csv` mapping the project roles (`g, admin, role:admin`).

## External identity providers (Google, GitHub, ...)

`identity_providers:` in the bootstrap config creates or updates one IdP template per entry (`google`, `github`, `azure`, `generic_oidc`) and adds it to the instance login policy, which is what puts the button on the login page. Client id and secret are read from the env vars named by `client_id_env` / `client_secret_env` (SealedSecret + `envFrom` on the Job); an entry without credentials is skipped. It is create-or-update, so changing an option and re-running the Job replays. Setting `enabled_in_login_policy: false` removes the button without deleting the template.

Every option is off by default. The safe setup for a closed set of users is `auto_linking: email` and nothing else: the first login with the external account is matched to the existing Zitadel user that has the same **verified** email and linked silently, so roles and grants stay on the same user. With no match nobody is created. `is_auto_creation: true` would let any account of that provider create a user.

Callback URL to register at the provider (login UI v1, Zitadel 2.x): `https://<zitadel-domain>/ui/login/login/externalidp/callback`.

A user who already has a second factor registered is still asked for it after an external login (the policy flag `forceMfaLocalOnly` only affects forced enrolment). The GitHub provider reads the email from GitHub's `/user` profile call, which may expose only the public email: if auto-linking does not match, make the GitHub primary email public and equal to the Zitadel one.

## Agentic use case

Service accounts enable AI agents to authenticate programmatically:

```python
import requests

# Agent authenticates with Zitadel using client credentials
token_response = requests.post(
    "https://zitadel.aitizate.com/oauth/v2/token",
    data={
        "grant_type": "client_credentials",
        "client_id": "agent-client-id",
        "client_secret": "agent-secret",
        "scope": "openid profile urn:zitadel:iam:org:project:roles",
    },
)
access_token = token_response.json()["access_token"]

# Agent calls protected API with token
response = requests.get(
    "https://api.aitizate.com/v1/models",
    headers={"Authorization": f"Bearer {access_token}"},
)
```

Combined with Crossplane, an agent can:
1. Authenticate via Zitadel service account
2. Create a Crossplane Claim for infrastructure
3. Access provisioned resources with its token
4. All governed by RBAC roles defined in git

## Troubleshooting

```bash
# Zitadel logs
kubectl logs -n zitadel deploy/zitadel

# PostgreSQL logs
kubectl logs -n zitadel statefulset/zitadel-postgres-postgresql

# Bootstrap job logs
kubectl logs -n zitadel job/zitadel-bootstrap

# Check OIDC discovery
curl https://zitadel.{domain}/.well-known/openid-configuration

# Check oauth2-proxy can reach Zitadel
kubectl logs -n security deploy/oauth2-proxy | grep -i oidc

# Verify token claims (decode JWT)
# After login, check X-Auth-Request-Groups header for roles
```

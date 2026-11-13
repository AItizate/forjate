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
├── kustomization.yaml              # Zitadel v4.20.2 (Helm chart 10.5.0) + Ingress
├── contract.yaml                   # THE list of what a tenant must provide
├── ingress.yaml                    # zitadel.example.com (patchable); /ui/v2/login -> zitadel-login
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

The chart's `init` and `setup` Jobs are Argo CD **Sync** hooks ordered with sync-waves (postgres 0, init 1, setup 2, Deployments `zitadel` and `zitadel-login` and Ingress 3). The bootstrap Job is a **PostSync** hook. No `helm.sh/hook*` annotation survives the render: Argo CD v3.6.1 treats the presence of the key as "this is a hook", even blank.

## What the tenant must provide

One contract, in `k8s/components/apps/auth/zitadel/contract.yaml`. The kustomization headers and this page repeat it, and `tests/zitadel/test_contract.py` fails if a rendered pod reads a Secret or key that the contract does not list.

**One namespace for everything**, set by the overlay with `namespace:` (the example uses `zitadel`). kustomize does not stamp `namespace:` on the Helm chart's objects, so the overlay forces it with a patch on `app.kubernetes.io/part-of=zitadel-stack` (every object of the bundle carries that label; the example shows the patch). Do not rely on Argo CD `destination.namespace` or `kubectl -n`: a root kustomization that holds several namespaces cannot use them.

**Secrets you create before the first sync** (SealedSecret or ESO):

| Secret | Keys | Read by |
|---|---|---|
| `zitadel-masterkey` | `masterkey` (32 characters) | Deployment `zitadel`, Job `zitadel-setup` |
| `zitadel-db-config` | `config-yaml`: Zitadel config merged **over** the chart's ConfigMap. It must hold **both** `Database.postgres.User.Password` and `Admin.Password` (v4 defaults the admin to `postgres`/`postgres`); it can also override `ExternalDomain` and `FirstInstance.Org.Human.Email` | `zitadel`, `zitadel-init`, `zitadel-setup` |
| `zitadel-postgres-secret` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (bundle only) | StatefulSet `zitadel-postgres` |
| `zitadel-admin-password` | `password`: the first admin's password. Required, there is no default. It must satisfy Zitadel's default password policy (at least 8 characters with upper case, lower case, a digit and a symbol) or setup fails on a new instance | `zitadel`, `zitadel-setup` |
| `zitadel-login-service-key` | `tls.crt`, `tls.key`: an RSA keypair (self-signed is fine, see the example). Zitadel verifies the Login V2 service's JWTs with `tls.crt`; the service signs with `tls.key`. Keep it stable: a new key on every build means a rollout on every sync | Deployments `zitadel` and `zitadel-login` |
| `zitadel-bootstrap-env` (optional) | one key per `*_env` name in `bootstrap.yaml`: IdP client id/secret, users' initial passwords | Job `zitadel-bootstrap` |

**Secrets that appear by themselves** (never create them by hand):

| Secret | Keys | Created by |
|---|---|---|
| `zitadel-admin-sa` | `zitadel-admin-sa.json` | the chart's setup Job, the first time it runs |
| `zitadel-oidc-<app>` | `client-id`, `issuer-url`, `client-secret` (no secret for public clients) | the bootstrap Job, one per entry of `applications:`, in the same namespace |

**The ConfigMap you replace:** `zitadel-bootstrap-config` (key `bootstrap.yaml`), with `configMapGenerator` + `behavior: replace` and **no** `namespace:` on the generator.

**The hostname**, in six places (the chart cannot be re-valued by a consumer): the Ingress host and TLS host, the Host header of the three probes of Deployment `zitadel`, the env `ZITADEL_EXTERNALDOMAIN` of Deployment `zitadel-login`, `ExternalDomain` in `zitadel-db-config`, and `instance_url` in `bootstrap.yaml`. The example overlay shows all of them as patches.

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

There is no default admin password and no manual step in the UI. Init and setup run again on every sync (they are idempotent: setup skips what already exists), which is the price of keeping them as recreatable hooks.

## First login

The first admin's login name is `admin@zitadel.<ExternalDomain>` (Zitadel suffixes the username with the organization domain), and its password is the value of `zitadel-admin-password`. Zitadel asks to change it at the first login. Use it to enrol a second factor and to create the people who will administer; day-to-day users come from `bootstrap.yaml`.

## Migrating an existing instance

For a tenant that already runs an earlier version of this component. The instance exists, Zitadel's `FirstInstance` never runs again, and the bootstrap service account key was created by hand. Do this **before** syncing the new version, or the Deployment stays in `CreateContainerConfigError` and the bootstrap Job stops at once with "the bootstrap service account key is missing".

1. **Create `zitadel-admin-password`.** The Deployment and the setup Job now require it. On an existing instance its value is never used (the first admin already exists), so a random one is fine:
   ```bash
   kubectl create secret generic zitadel-admin-password -n zitadel \
     --from-literal=password="$(openssl rand -base64 24)Aa1!"
   ```
2. **Re-key the bootstrap service account Secret.** The chart writes `zitadel-admin-sa.json`; the old guide had you store the key as `sa-key.json`. The bootstrap Job reads only the new name:
   ```bash
   kubectl get secret zitadel-admin-sa -n zitadel -o jsonpath='{.data.sa-key\.json}' | base64 -d > key.json
   kubectl create secret generic zitadel-admin-sa -n zitadel \
     --from-file=zitadel-admin-sa.json=key.json --dry-run=client -o yaml | kubectl apply -f -
   rm key.json
   ```
   If you keep the Secret in git as a SealedSecret, seal it under the new key name instead.
3. **Close the old default admin.** Earlier versions created `zitadel-admin` with the Zitadel default password, behind the public Ingress. If it was never changed, anyone can log in as IAM_OWNER. In the Console create your own admin (or use the one from `bootstrap.yaml`), then change or deactivate `zitadel-admin`, and audit the instance's logins since the first deploy.
4. **Remove what the old version left.** The cluster-scoped role and binding named `zitadel-bootstrap` (`kubectl delete clusterrole,clusterrolebinding zitadel-bootstrap`; Argo CD prunes them if it tracks them), the `rbac/` entry in your overlay's `resources`, and, if Argo complains about immutable fields on the first sync, the old plain Jobs `zitadel-init` and `zitadel-setup` (they are Argo CD hooks now and are recreated).
5. **Adapt `bootstrap.yaml`.** `initial_password:` literals are rejected (use `initial_password_env`), `organization:` becomes `organizations:`, and an Azure IdP needs `tenant_id`. The Job exits 2 and lists every `CONFIG ERROR`.
6. **Namespace patch and labels.** Add the namespace patch of the example overlay; the bundle keeps `part-of: zitadel-stack`, so an existing selector on it still works.

## Recovering the bootstrap service account key

On a **new** instance the chart's setup Job writes the key to `zitadel-admin-sa` itself. If the Secret is missing anyway (the writer container failed, the Secret was deleted, or `kubectl create` found one already there), `FirstInstance` will not run again to rewrite it. Create a new key by hand:

1. Log in to the Console as the first admin (`admin@zitadel.<ExternalDomain>`).
2. Users → Service Users → `zitadel-admin-sa` (IAM_OWNER, created by `FirstInstance`). On an instance without it, create a service user and give it the `IAM_OWNER` role under Instance → Members.
3. Keys → New → JSON, download it, and store it:
   ```bash
   kubectl create secret generic zitadel-admin-sa -n zitadel --from-file=zitadel-admin-sa.json=./key.json
   ```
4. Delete the downloaded file, and delete any older key of that user in the Console. Re-run the bootstrap (`kubectl delete job zitadel-bootstrap -n zitadel`, or sync).

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
  --from-literal=password="$(openssl rand -base64 24)Aa1!"   # Zitadel's policy wants upper, lower, digit and symbol
```

`zitadel-postgres-secret`, `zitadel-db-config` and `zitadel-bootstrap-env` follow the same pattern; see the example files. The Zitadel DB passwords in `zitadel-db-config` must equal `POSTGRES_PASSWORD`. For anything beyond a lab, seal them (or use ESO) instead of applying them with `kubectl`.

### Step 2: Copy and adapt the example overlay

Copy `docs/examples/zitadel-tenant/` into your tenant repo, change the domain in the places marked `HOSTNAME`, and edit `bootstrap.yaml`. For a remote tenant, point the first resource at `ssh://git@github.com/AItizate/forjate.git//k8s/components/bundles/zitadel-stack?ref=<tag>`.

### Step 3: Sync

```bash
kustomize build --enable-helm docs/examples/zitadel-tenant | kubectl apply -f -
```

or let Argo CD do it. Init, setup, the Deployment and the bootstrap Job run in order by themselves; the key of the bootstrap service account is written by the chart.

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

## Version, licence and telemetry: Zitadel v4.20.2

The component pins **chart 10.5.0** and overrides `image.tag` to **Zitadel v4.20.2** (the chart's own app version is v4.19.2). The pin is the latest stable on purpose: v4.15.3 fixed **CVE-2026-56666** (auto-linking an external login by email did not check that the IdP verified the email), but later releases closed more advisories in Login V1 and Actions V1, so the lowest version without a known advisory is **v4.19.5**. Skip **v4.18.0** (its setup step fails).

- **Licence:** AGPL-3.0-only from v3 (v2 was Apache-2.0); a commercial licence exists. Running it unmodified and only talking to its API is the use this component makes of it. Not legal advice: check it against how you distribute the stack.
- **Service Ping** (usage reports to `zitadel.com`, on by default since v4.0.0) is off: `ServicePing.Enabled: false`.
- **Login V2** is the login UI. A new instance gets it from `DefaultInstance.Features.LoginV2.Required: true`, which is the only place the first instance reads features from. It runs as Deployment `zitadel-login` (port 3000) behind `/ui/v2/login`.
- The bootstrap refuses `auto_linking: email` for `azure` and `generic_oidc` (unless `trust_idp_email: true`) and `auto_linking: username` for every provider (unless `trust_idp_username: true`). That is policy, kept after the fix: an email or username claim from a loose IdP is not proof of identity.
- Keep `is_auto_creation` off unless you really want anyone with an account at the provider to get a user.
- **Actions v1** (the `groups` claim of the bootstrap) still works in v4 but is planned for removal in Zitadel v5; replacing it with Actions v2 (an external webhook; in-cluster webhooks are blocked by the default `HTTPClient.DenyList` of private networks) is a follow-up. The bootstrap also uses the v1 management/admin APIs, deprecated but served.
- Postgres 14 to 18 is supported; the bundle's `postgres:16` needs no change.
- Zitadel v4.19.5+ rejects requests whose `Host` is not an instance domain: Traefik must forward the public host (it does by default), and in-cluster callers (probes, the bootstrap Job) send it explicitly.

## Upgrading to v4 (an existing v2.x instance)

The database migration runs in the setup hook and **cannot be undone by reverting git**: migrations are forward only. Take a `pg_dump -Fc` of the Zitadel database and keep the masterkey before you sync; restoring that dump is the only way back (everything written to Zitadel afterwards is lost).

1. **Path.** Upstream recommends v3.4.x (at least 3.4.1), a soak, then v4, because v4 makes OIDC web keys mandatory (advisory A-10017). No chart ships v3 and v3 is end of life. A direct v2.67.2 to v4 jump works (`zitadel setup` is incremental, with no version guard) at one price: **every existing token is invalid, so everybody must log in again**, and a Console logout may fail on `id_token_hint` until the browser state is cleared. Plan a window.
2. **Immutable Deployment selector.** Chart 10 adds `component: start` to the selector of `Deployment zitadel` (apps/v1 selectors are immutable), so syncing over an existing Deployment fails with "field is immutable". Add a patch to the overlay that removes `component: start` from `spec.selector.matchLabels` (the pod template keeps the label, so the selector stays a valid subset), or delete the Deployment once. `Service zitadel`'s selector is mutable.
3. **Sync order.** The migration runs in the setup hook (wave 2), before the Deployment is replaced (wave 3): the old pod keeps serving against a database that is being migrated for a short while.
4. **Login V2 on an instance that existed.** An upgrade keeps Login V1 (`DefaultInstance` is not read again). To adopt V2 put `features: {login_v2: true}` in `bootstrap.yaml`; the bootstrap sets the instance feature `loginV2.required`. **Change the callback URL at every external IdP first or at the same time:** V1 used `https://<zitadel-domain>/ui/login/login/externalidp/callback`, V2 uses `https://<zitadel-domain>/idps/callback`. A GitHub OAuth App accepts only one callback URL, so replace it; at Google add the new redirect URI.
5. **Whether the Actions v1 `groups` claim fires for Login V2 sessions** is not documented: check `groups` in the token after the upgrade.
6. **A leftover Job with the same name blocks the new hooks.** Argo CD reads a hook's delete policy from the LIVE object. If `zitadel-init`, `zitadel-setup` or `zitadel-bootstrap` already exist as completed Jobs **without** hook annotations (they were created by something other than this component's hooks), `BeforeHookCreation` never fires: the old Job counts as the hook that already ran, the new hook is skipped and the Deployment is applied **without the database migration** (the v4 pod then crashes with `relation "queue.river_queue" does not exist`). Delete such Jobs before the first sync; once the hooks own them, every sync recreates them.
7. **Secrets the component reads must exist and be owned by whatever manages them** before the first sync (see "What the tenant must provide"). A Secret that was created by hand under the same name can be refused by a controller that wants to own it; resolve that on the tenant side.
8. The other steps of "Migrating an existing instance" above (the Secrets, the bootstrap service account key) still apply.

An existing v2.67.2 database (827 events) was migrated to v4.20.2 by the `zitadel-setup` hook in about a minute, and the `groups` claim of the bootstrap's Actions v1 flow kept working under Login V2.

## OIDC clients for Argo CD and other apps

The bootstrap creates every application listed under `applications:` and updates the ones that exist (redirect URIs, auth method, role assertions). It logs the `clientId` of every app and stores `zitadel-oidc-<app>` (`client-id`, `issuer-url`, and `client-secret` for confidential clients) in the bootstrap namespace. Seal or copy the secret into the namespace that consumes it.

Zitadel emits roles as an object under `urn:zitadel:iam:org:project:roles`. Argo CD and oauth2-proxy only read claims that are flat lists, so define an action that adds a `groups` claim and attach it to the Complement Token flow (see the commented `actions:` / `flows:` example in the bootstrap ConfigMap). Create it with `allowed_to_fail: true`: a failing action that is not allowed to fail blocks every login. The example keeps only the grants of the configured project: the bootstrap replaces `{{project_id}}` in the action script with the id of `project:`, so a role named `viewer` in another project does not pass oauth2-proxy's `allowed-group` gate. (It relies on `projectId` being present on the user grants in the Actions v1 context; check it once on a live instance.)

Argo CD, two clients:

| App | Type | Auth method | Redirect URI |
|---|---|---|---|
| `argocd` | WEB (default) | BASIC (secret) | `https://<argocd>/auth/callback` |
| `argocd-cli` | `OIDC_APP_TYPE_NATIVE` | `OIDC_AUTH_METHOD_TYPE_NONE` (PKCE) | `http://localhost:8085/auth/callback` |

`argocd-cm`: `oidc.config` with `issuer`, `clientID`, `clientSecret: $<sealed-secret>:client-secret` (the Secret needs the label `app.kubernetes.io/part-of: argocd`), `cliClientID`, `enablePKCEAuthentication: true`, `requestedScopes: [openid, profile, email, groups]`. `argocd-rbac-cm`: `scopes: '[groups]'` and `policy.csv` mapping the project roles (`g, admin, role:admin`).

## External identity providers (Google, GitHub, ...)

`identity_providers:` in the bootstrap config creates or updates one IdP template per entry (`google`, `github`, `azure`, `generic_oidc`) and adds it to the **instance** login policy, which is what puts the button on the login page for every organization that uses the instance default policy. Client id and secret are read from the env vars named by `client_id_env` / `client_secret_env` (they live in `zitadel-bootstrap-env`); an entry without credentials is skipped, loudly. It is create-or-update, so changing an option and re-running the Job replays. `enabled_in_login_policy: false` removes the button without deleting the template. Removing the entry from the YAML removes nothing.

Every option is off by default. The setup for a closed set of users is `auto_linking: email` and nothing else: the first login with the external account is matched to the existing Zitadel user that has the same **verified** email and linked silently, so roles and grants stay on the same user. With no match nobody is created. Read "Version, licence and telemetry" above first.

Safe defaults the script enforces:

- **azure** needs `tenant_id` (your Entra tenant) or an explicit `tenant_type`; there is no default, because `COMMON` accepts any Microsoft account. `email_verified` defaults to `false`: an Entra `email` claim is user-editable.
- **`auto_linking: email` on `azure` and `generic_oidc` is refused** (config error, exit 2) unless the entry sets `trust_idp_email: true`: the email claim of an Entra tenant or a generic OIDC server is not proof of identity, and linking on it hands over the Zitadel user with that email, admins included.
- **`auto_linking: username` is refused for every provider** (`github`, `google`, `azure`, `generic_oidc`) unless the entry sets `trust_idp_username: true`: a username is chosen by whoever registers it. Anyone could register the GitHub login `admin`, or the login of a user in your closed set, and be linked to that Zitadel user on first login with its grants. Use `email` on Google and GitHub.

Callback URL to register at the provider: with Login V2 (the default of this component) `https://<zitadel-domain>/idps/callback`; with Login V1 (an instance that never adopted V2) `https://<zitadel-domain>/ui/login/login/externalidp/callback`.

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

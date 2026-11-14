# Zitadel

## Overview

Zitadel is a cloud-native Identity Provider (IdP) that provides user management, authentication (OIDC/SAML), RBAC, and service accounts, all API-first. This component runs it with its own PostgreSQL (the bundle composes the postgres component) and a bootstrap Job that keeps organizations, projects, roles, OIDC clients, users, service users and external identity providers as code.

The component stands on its own: it does not reference, require or configure any other component. Whatever consumes Zitadel (an auth proxy, a CI system, an app) is wired by the tenant overlay; recipes are in [`docs/tenant-onboarding/zitadel-integrations.md`](../tenant-onboarding/zitadel-integrations.md).

**Delivery requirement: Argo CD.** The init/setup/bootstrap Jobs are Argo CD hooks ordered with sync-waves (`argocd.argoproj.io/*` annotations). Delivered by Argo CD they run in order by themselves. Applied with plain `kubectl apply` the annotations do nothing: the three Jobs run as ordinary Jobs at the same time as the Deployment, so there is no Argo-free automatic path. Apply in order by hand instead: postgres, then Job `zitadel-init`, then Job `zitadel-setup`, then the Deployments, then Job `zitadel-bootstrap` (delete each finished Job before re-applying it).

## Architecture: How it fits

```
┌──────────────────────────────────────────────────────────┐
│  Zitadel (namespace of the tenant overlay)               │
│  ├── IdP: user database, authentication, JWT issuance    │
│  ├── Login V2 (zitadel-login) behind /ui/v2/login        │
│  ├── RBAC: organizations → projects → roles              │
│  ├── Service accounts: machine-to-machine tokens         │
│  └── Admin API: gRPC + REST (for the bootstrap Job)      │
└────────────────────┬─────────────────────────────────────┘
                     │ OIDC (issuer)
                     ▼
        OIDC clients (any relying party)
   client id/secret in Secret zitadel-oidc-<app>,
   written by the bootstrap for each entry of `applications:`
```

## Zitadel concepts → Forjate mapping

| Zitadel | Factory equivalent | Example |
|---|---|---|
| Organization | Tenant | acme, customers |
| Project | App group | platform |
| Application | OIDC client | web-app, cli-app |
| Role | Access level | admin, operator, viewer |
| Human User | Person | ana, dev-user |
| Service User | Machine account | pipeline, agent |

## Component structure

```
k8s/components/apps/auth/zitadel/
├── kustomization.yaml              # Zitadel v4.20.2 (Helm chart 10.5.0) + Ingress
├── contract.yaml                   # THE list of what a tenant must provide
├── ingress.yaml                    # zitadel.example.com (patchable); /ui/v2/login -> zitadel-login
├── bootstrap/                      # IaC: orgs, project, roles, apps, users, IdPs
│   ├── kustomization.yaml
│   ├── job.yaml                    # PostSync Job (runs bootstrap.py)
│   ├── bootstrap.py                # the reconciler (tested, see ../tests/)
│   ├── requirements.txt            # pinned dependencies of bootstrap.py
│   ├── configmap.yaml              # desired state placeholder (the tenant replaces it)
│   ├── serviceaccount.yaml
│   ├── role.yaml                   # secrets get/create/patch, own namespace only
│   └── rolebinding.yaml
└── tests/                          # pytest: render, contract, bootstrap.py against a mock (CI: validate-zitadel.yml)

k8s/components/bundles/zitadel-stack/   # chart + postgres + bootstrap in one reference
docs/examples/zitadel-tenant/           # a tenant overlay that CI builds
```

The tests live inside the component, next to the script and the contract they check, so they travel with it and run when only the component changes. Kustomize never reads them (a component builds only what its `kustomization.yaml` lists) and `wiki-compile.py` ignores them. Run them with `poetry run pytest k8s/components/apps/auth/zitadel/tests`.

The chart's `init` and `setup` Jobs are Argo CD **Sync** hooks ordered with sync-waves (postgres 0, init 1, setup 2, Deployments `zitadel` and `zitadel-login` and Ingress 3). The bootstrap Job is a **PostSync** hook. No `helm.sh/hook*` annotation survives the render: Argo CD v3.6.1 treats the presence of the key as "this is a hook", even blank.

## What the tenant must provide

One contract, in `k8s/components/apps/auth/zitadel/contract.yaml`. The kustomization headers and this page repeat it, and `k8s/components/apps/auth/zitadel/tests/test_contract.py` fails if a rendered pod reads a Secret or key that the contract does not list.

**One namespace for everything**, set by the overlay with `namespace:` (the example uses `zitadel`). With chart 10 the Helm objects render with `namespace: default` and the overlay's `namespace:` replaces it, so setting `namespace:` is enough (`test_overlay_namespace_reaches_the_helm_objects` proves it). The example also keeps a patch on `app.kubernetes.io/part-of=zitadel-stack` (every object of the bundle carries that label) as a safeguard, for example if you pin an older chart whose objects render without a namespace. Do not rely on Argo CD `destination.namespace` or `kubectl -n`: a root kustomization that holds several namespaces cannot use them.

**Secrets you create before the first sync** (however the tenant manages secrets):

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
  - name: web-app
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

The first admin's login name is the FirstInstance username **as rendered**: `admin@zitadel.<ExternalDomain>` (Zitadel suffixes the username `admin` with the domain of the instance's first organization, so on `secure.example.com` it is `admin@zitadel.secure.example.com`; typing just `admin` finds nothing). Its password is the value of `zitadel-admin-password`. Zitadel asks to change it at the first login. Use it to enrol a second factor and to create the people who will administer; day-to-day users come from `bootstrap.yaml`.

**Give the first admin an email nobody else uses.** `FirstInstance.Org.Human.Email.Address` (override it in `zitadel-db-config`, the example uses `zitadel-admin@acme.dev`) must differ from the email of every other human user, above all the people in `bootstrap.yaml`. The first admin lives in its own organization (`ZITADEL`), so Zitadel accepts the duplicate, but with `auto_linking: email` the first Google/GitHub login of that person matches two users and ends in "account not found". When an IdP links by email the bootstrap checks this on every run and **fails** (exit 1, `email ... belongs to 2 users`) until one of the two emails changes. A plus-address (`you+zitadel-admin@gmail.com`) is enough and still reaches your inbox. On an instance that already exists, change the email of the live admin in the Console (or `POST /v2/users/{id}/email` with `isVerified: true`) and also in `zitadel-db-config`, so a rebuilt instance gets the same value.

## Adopting an existing Zitadel instance

For a Zitadel instance that this component's setup hook did not create (it was installed some other way, or an earlier setup already ran): Zitadel's `FirstInstance` never runs again, so the bootstrap service account key does not come from the chart. Do this **before** syncing, or the Deployment stays in `CreateContainerConfigError` and the bootstrap Job stops at once with "the bootstrap service account key is missing".

1. **Create `zitadel-admin-password`.** The Deployment and the Jobs require it. On an existing instance its value is never used (the first admin already exists), so a random one is fine:
   ```bash
   kubectl create secret generic zitadel-admin-password -n zitadel \
     --from-literal=password="$(openssl rand -base64 24)Aa1!"
   ```
2. **Provide the bootstrap service account key** as the Secret `zitadel-admin-sa`, key `zitadel-admin-sa.json` (the JSON key of an `IAM_OWNER` service user); see "Recovering the bootstrap service account key" below. The bootstrap Job reads only that name and key.
3. **Close a first admin that kept Zitadel's built-in password.** A Zitadel that was set up without `FirstInstance` creates `zitadel-admin` with the documented default password. If it was never changed and the instance is reachable, anyone can log in as `IAM_OWNER`: create your own admin in the Console, change or deactivate `zitadel-admin`, and audit the logins since the first deploy.
4. **Adapt `bootstrap.yaml`.** `initial_password:` literals are rejected (use `initial_password_env`), the list is `organizations:` (the singular form is deprecated), and an Azure IdP needs `tenant_id`. The Job exits 2 and lists every `CONFIG ERROR`.
5. **Set the overlay `namespace:`** (and keep the labels the bundle sets) so every object, the chart's included, lands in the namespace that holds the Secrets.

## Recovering the bootstrap service account key

On a **new** instance the chart's setup Job writes the key to `zitadel-admin-sa` itself. If the Secret is missing anyway (the writer container failed, the Secret was deleted, or `kubectl create` found one already there), `FirstInstance` will not run again to rewrite it. Create a new key by hand:

1. Log in to the Console as the first admin (`admin@zitadel.<ExternalDomain>`).
2. Users → Service Users → `zitadel-admin-sa` (IAM_OWNER, created by `FirstInstance`). On an instance without it, create a service user and give it the `IAM_OWNER` role under Instance → Members.
3. Keys → New → JSON, download it, and store it:
   ```bash
   kubectl create secret generic zitadel-admin-sa -n zitadel --from-file=zitadel-admin-sa.json=./key.json
   ```
4. Delete the downloaded file, and delete any older key of that user in the Console. Re-run the bootstrap (`kubectl delete job zitadel-bootstrap -n zitadel`, or sync).

## Ingress: tenant patch points

`ingress.yaml` is deliberately plain: host, TLS secret name and two paths (`/ui/v2/login` to `zitadel-login:3000`, `/` to `zitadel:8080`). It carries no certificate-issuer or ingress-controller annotations and no `ingressClassName`, because those are the tenant's choices. Patch them in the overlay (the example overlay does): `cert-manager.io/cluster-issuer: <issuer>` if cert-manager issues the certificate, `ingressClassName`, controller annotations (for Traefik, `traefik.ingress.kubernetes.io/router.entrypoints` and middlewares), and the host and TLS host.

## Setup guide

### Prerequisites

- Kubernetes cluster with an ingress controller (any) and, if you want TLS from an issuer, whatever issues your certificates (tenant choice, see "Ingress: tenant patch points")
- `kustomize` with `--enable-helm` (Argo CD: `kustomize.buildOptions: --enable-helm`)
- A domain for Zitadel (e.g., `zitadel.acme.dev`)
- Free capacity for the Postgres volume (10Gi by default). A storage provisioner with a scheduling reserve (Longhorn is one: `insufficient storage` on a PVC that finds no node with room for its replicas) leaves `zitadel-postgres-0` `Pending`, which is easy to mistake for a Zitadel problem. Before the first sync check the provisioner's free capacity (for Longhorn: *Node* in its UI, or `kubectl get nodes.longhorn.io -n longhorn-system`) and free or grow storage first: delete retired PVCs, lower the replica count, add disks.
- `kustomize build --enable-helm` writes the downloaded chart to `charts/` next to the kustomization that declares it. That directory is a cache: keep `**/charts/` in the tenant's `.gitignore` (this repository's `.gitignore`, the use-case template and `init-tenant.py` already do) and never commit it.

### Step 1: Create the secrets

Create the Secrets of the contract in the overlay's namespace. The example recipe (one `.env` per Secret, sealed with `kubeseal` as one possible tool) is in `docs/examples/zitadel-tenant/secrets/README.md`. In short:

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

Let Argo CD deliver the overlay (the hooks need it, see "Delivery requirement" in the overview). Init, setup, the Deployments and the bootstrap Job then run in order by themselves; the key of the bootstrap service account is written by the chart. Without Argo CD, apply in the order described there.

### Step 4: Verify

```bash
kubectl get pods -n zitadel
kubectl logs -n zitadel job/zitadel-bootstrap          # ends with "Bootstrap complete"
kubectl get secret zitadel-oidc-<app> -n zitadel      # one per entry of `applications:`
curl https://zitadel.acme.dev/.well-known/openid-configuration
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
- Zitadel v4.19.5+ rejects requests whose `Host` is not an instance domain: the ingress controller must forward the public host (most do by default), and in-cluster callers (probes, the bootstrap Job) send it explicitly.

## Upgrading to v4 (an existing v2.x instance)

The database migration runs in the setup hook and **cannot be undone by reverting git**: migrations are forward only. Take a `pg_dump -Fc` of the Zitadel database and keep the masterkey before you sync; restoring that dump is the only way back (everything written to Zitadel afterwards is lost).

1. **Path.** Upstream recommends v3.4.x (at least 3.4.1), a soak, then v4, because v4 makes OIDC web keys mandatory (advisory A-10017). No chart ships v3 and v3 is end of life. A direct v2.67.2 to v4 jump works (`zitadel setup` is incremental, with no version guard) at one price: **every existing token is invalid, so everybody must log in again**, and a Console logout may fail on `id_token_hint` until the browser state is cleared. Plan a window.
2. **Immutable Deployment selector.** Chart 10 adds `component: start` to the selector of `Deployment zitadel` (apps/v1 selectors are immutable), so syncing over an existing Deployment fails with "field is immutable". Add a patch to the overlay that removes `component: start` from `spec.selector.matchLabels` (the pod template keeps the label, so the selector stays a valid subset), or delete the Deployment once. `Service zitadel`'s selector is mutable.
3. **Sync order.** The migration runs in the setup hook (wave 2), before the Deployment is replaced (wave 3): the old pod keeps serving against a database that is being migrated for a short while.
4. **Login V2 on an instance that existed.** An upgrade keeps Login V1 (`DefaultInstance` is not read again). To adopt V2 put `features: {login_v2: true}` in `bootstrap.yaml`; the bootstrap sets the instance feature `loginV2.required`. **Change the callback URL at every external IdP first or at the same time:** V1 used `https://<zitadel-domain>/ui/login/login/externalidp/callback`, V2 uses `https://<zitadel-domain>/idps/callback`. A GitHub OAuth App accepts only one callback URL, so replace it; at Google add the new redirect URI.
5. **Whether the Actions v1 `groups` claim fires for Login V2 sessions** is not documented: check `groups` in the token after the upgrade.
6. **A leftover Job with the same name blocks the new hooks.** Argo CD reads a hook's delete policy from the LIVE object. If `zitadel-init`, `zitadel-setup` or `zitadel-bootstrap` already exist as completed Jobs **without** hook annotations (they were created by something other than this component's hooks), `BeforeHookCreation` never fires: the old Job counts as the hook that already ran, the new hook is skipped and the Deployment is applied **without the database migration** (the v4 pod then crashes with `relation "queue.river_queue" does not exist`). Delete such Jobs before the first sync; once the hooks own them, every sync recreates them.
7. **Secrets the component reads must exist and be owned by whatever manages them** before the first sync (see "What the tenant must provide"). A Secret that was created by hand under the same name can be refused by a controller that wants to own it; resolve that on the tenant side.
8. The other steps of "Adopting an existing Zitadel instance" above (the Secrets, the bootstrap service account key) still apply.

### External identity providers (Google, GitHub, ...)

`identity_providers:` in the bootstrap config creates or updates one IdP template per entry (`google`, `github`, `azure`, `generic_oidc`) and adds it to the **instance** login policy, which is what puts the button on the login page for every organization that uses the instance default policy. Client id and secret are read from the env vars named by `client_id_env` / `client_secret_env` (they live in `zitadel-bootstrap-env`); an entry without credentials is skipped, loudly. It is create-or-update, so changing an option and re-running the Job replays. `enabled_in_login_policy: false` removes the button without deleting the template. Removing the entry from the YAML removes nothing.

Every option is off by default. The setup for a closed set of users is `auto_linking: email` and nothing else: the first login with the external account is matched to the existing Zitadel user that has the same **verified** email and linked silently, so roles and grants stay on the same user. With no match nobody is created. Read "Version, licence and telemetry" above first.

Safe defaults the script enforces:

- **azure** needs `tenant_id` (your Entra tenant) or an explicit `tenant_type`; there is no default, because `COMMON` accepts any Microsoft account. `email_verified` defaults to `false`: an Entra `email` claim is user-editable.
- **`auto_linking: email` on `azure` and `generic_oidc` is refused** (config error, exit 2) unless the entry sets `trust_idp_email: true`: the email claim of an Entra tenant or a generic OIDC server is not proof of identity, and linking on it hands over the Zitadel user with that email, admins included.
- **`auto_linking` turns linking on.** Zitadel ignores `autoLinking` while the IdP's `isLinkingAllowed` is off, and the login page then says "cannot link" with no error anywhere in the API. So `is_linking_allowed` defaults to `true` when `auto_linking` is set, and `auto_linking` together with an explicit `is_linking_allowed: false` is a config error (exit 2). Without `auto_linking` the default stays `false`. `is_creation_allowed` and `is_auto_creation` stay off: linking never creates users.
- **Emails must be unique across human users** when any IdP uses `auto_linking: email`. The bootstrap lists the human users after it has applied the config and fails the run when two share an email (typical case: the first admin and a person in `bootstrap.yaml`, see "First login"). The check runs on every replay, so it keeps reporting until fixed.
- **`auto_linking: username` is refused for every provider** (`github`, `google`, `azure`, `generic_oidc`) unless the entry sets `trust_idp_username: true`: a username is chosen by whoever registers it. Anyone could register the GitHub login `admin`, or the login of a user in your closed set, and be linked to that Zitadel user on first login with its grants. Use `email` on Google and GitHub.

### Self-registration

Zitadel's instance login policy ships with `allowRegister=true`: anyone who can reach the login page may create a local account. The bootstrap switches it **off** on every run (`GET` then `PUT /admin/v1/policies/login`, the rest of the policy is written back as it is, no call when it already matches). To keep registration open, opt in:

```yaml
login_policy:
  allow_register: true
```

Only the instance default policy is managed. An organization that has a login policy of its own (Console: *Settings > Login Behaviour > Override*) overrides it and must be checked there. Users created by `is_creation_allowed` / `is_auto_creation` on an IdP are a separate path and stay off by default.

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
```

| Symptom | Likely cause |
|---|---|
| Pods in `CreateContainerConfigError` | a Secret of the contract is missing (`zitadel-masterkey`, `zitadel-admin-password`, `zitadel-db-config`) |
| `zitadel` Deployment never starts, init/setup Jobs absent | `helm.sh/hook*` annotation back in the render; `k8s/components/apps/auth/zitadel/tests/test_render.py` guards this |
| Bootstrap: `Failed to get an access token` | `instance_url` is not the issuer (it is the JWT audience and the Host header) |
| Bootstrap: exit 2 | `CONFIG ERROR` lines on stderr: literal `initial_password`, azure without tenant, `auto_linking: email` on azure/generic_oidc, `auto_linking: username` anywhere |
| Google/GitHub login says "cannot link" / "linking is not enabled" | the IdP was created with `isLinkingAllowed=false` (an older bootstrap, or `is_linking_allowed: false`); re-run the bootstrap with `auto_linking` set |
| Google/GitHub login says "account not found" although the user exists | two human users share the verified email (first admin vs an org user); the bootstrap now reports it as `email ... belongs to 2 users` |
| `zitadel-postgres-0` `Pending`, event `insufficient storage` (Longhorn) | no node can take the new PVC; see "Prerequisites" |
| Bootstrap: `FAILED: email ... belongs to N users` | see "First login" |
| `zitadel-admin-sa` missing | setup ran before and the key was not written; see the `zitadel-machinekey` container log. Recreate the machine key in the Console and store it under the same name and key |

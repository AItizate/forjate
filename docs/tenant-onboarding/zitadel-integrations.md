# Zitadel integrations (tenant wiring)

Wiring between the Zitadel component and other components is **tenant work**, not component work: the `auth/zitadel` component knows nothing about oauth2-proxy, Argo CD or any other consumer (see "Component Independence" in `CLAUDE.md`). This page collects the recipes. The component side is documented in [`docs/apps/zitadel.md`](../apps/zitadel.md) and its contract in `k8s/components/apps/auth/zitadel/contract.yaml`.

Zitadel's `zitadel-oidc-<app>` Secrets are written by the bootstrap Job **in the Zitadel namespace**, one per entry of `applications:`. A consumer in another namespace needs a copy of that Secret (SealedSecret, ESO, a reflector) or has to run in the same namespace.

## What Zitadel solves compared with oauth2-proxy and GoTrue

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



## Architecture with oauth2-proxy

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


## oauth2-proxy: switch the provider to Zitadel

Template: [`docs/examples/oauth2-proxy-with-zitadel/`](../examples/oauth2-proxy-with-zitadel/) (values file and the matching `applications:` entry for the bootstrap).

```bash
cp k8s/components/apps/auth/zitadel/oauth2-proxy-integration/oauth2-values-zitadel.yaml \
   k8s/overlays/{tenant}/oauth2-values.yaml
```

Update `oidc-issuer-url`, `redirect-url`, `cookie-domain`, `whitelist-domain`. The template reads the Secret `zitadel-oidc-oauth2-proxy`, which the bootstrap creates **in the Zitadel namespace**: copy it to oauth2-proxy's namespace (SealedSecret, ESO, reflector) or run both in one namespace. TLS to Zitadel is verified; the template no longer sets `ssl-insecure-skip-verify`. It reads the `groups` claim, so define the `groupsClaim` action (below).


# OIDC clients for Argo CD and other apps

The bootstrap creates every application listed under `applications:` and updates the ones that exist (redirect URIs, auth method, role assertions). It logs the `clientId` of every app and stores `zitadel-oidc-<app>` (`client-id`, `issuer-url`, and `client-secret` for confidential clients) in the bootstrap namespace. Seal or copy the secret into the namespace that consumes it.

Zitadel emits roles as an object under `urn:zitadel:iam:org:project:roles`. Argo CD and oauth2-proxy only read claims that are flat lists, so define an action that adds a `groups` claim and attach it to the Complement Token flow (see the commented `actions:` / `flows:` example in the bootstrap ConfigMap). Create it with `allowed_to_fail: true`: a failing action that is not allowed to fail blocks every login. The example keeps only the grants of the configured project: the bootstrap replaces `{{project_id}}` in the action script with the id of `project:`, so a role named `viewer` in another project does not pass oauth2-proxy's `allowed-group` gate. (It relies on `projectId` being present on the user grants in the Actions v1 context; check it once on a live instance.)

Argo CD, two clients:

| App | Type | Auth method | Redirect URI |
|---|---|---|---|
| `argocd` | WEB (default) | BASIC (secret) | `https://<argocd>/auth/callback` |
| `argocd-cli` | `OIDC_APP_TYPE_NATIVE` | `OIDC_AUTH_METHOD_TYPE_NONE` (PKCE) | `http://localhost:8085/auth/callback` |

`argocd-cm`: `oidc.config` with `issuer`, `clientID`, `clientSecret: $<sealed-secret>:client-secret` (the Secret needs the label `app.kubernetes.io/part-of: argocd`), `cliClientID`, `enablePKCEAuthentication: true`, `requestedScopes: [openid, profile, email, groups]`. `argocd-rbac-cm`: `scopes: '[groups]'` and `policy.csv` mapping the project roles (`g, admin, role:admin`).


# Replacing GoTrue

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


## Troubleshooting a consumer

```bash
# Check oauth2-proxy can reach Zitadel
kubectl logs -n security deploy/oauth2-proxy | grep -i oidc
```

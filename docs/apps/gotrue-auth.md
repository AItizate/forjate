# Gotrue Auth

Authentication and authorization stack based on [Supabase GoTrue](https://github.com/supabase/gotrue) (v2.188.1). Provides Google OAuth (and optionally GitHub, etc.) with per-app RBAC via JWT claims. Can coexist with `oauth2-proxy` — apps choose which auth chain to use via Traefik annotation.

## How it works

```
User → App (no token)
  → Traefik forward-auth → gotrue-authz → 302 redirect to GoTrue /authorize
  → GoTrue → Google OAuth → callback → GoTrue sets cookie → redirect back to App

User → App (with cookie)
  → Traefik forward-auth → gotrue-authz → validates token → 200 + user headers
  → Request passes to app with X-Auth-Request-Email, X-Auth-Request-User
```

When a user doesn't have access to a specific app (RBAC), gotrue-authz returns 403 with an access denied page.

## Component structure

**Path:** `k8s/components/apps/auth/gotrue-auth/`

| Sub-component | What it does |
|---|---|
| `gotrue/` | Supabase GoTrue server — OAuth providers, JWT issuer, user DB in Postgres |
| `authz/` | Node.js service — validates JWT, checks per-app RBAC, handles login redirects |
| `middlewares/` | Traefik middleware `gotrue-auth` (forwardAuth to authz) |

### Dependencies

- **Postgres** — GoTrue stores users in a dedicated database. Add the `databases/postgres` component to the same namespace.

## Differences vs oauth2-proxy

| | oauth2-proxy | gotrue-auth |
|---|---|---|
| **User management** | Static email list in config (requires redeploy) | User DB in Postgres — dynamic via API |
| **RBAC** | Per-tenant only | Per-app via `app_metadata.apps` |
| **Token** | Session cookie (opaque) | Standard JWT (verifiable by apps) |
| **OAuth providers** | Many built-in | Google, GitHub, and [20+ more](https://supabase.com/docs/guides/auth/social-login) via env vars |
| **Audit** | No | Login events in GoTrue logs |

## Tenant setup

### 1. Add components to overlay

```yaml
# In your namespace kustomization.yaml (e.g., security/)
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/databases/postgres?ref=<version>
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/auth/gotrue-auth?ref=<version>
```

### 2. Secrets (SealedSecrets replacing factory placeholders)

**postgres-secret:**
```
POSTGRES_USER=gotrue
POSTGRES_PASSWORD=<random>
POSTGRES_DB=gotrue_auth
```

**gotrue-secret:**
```
DATABASE_URL=postgres://gotrue:<password>@postgres:5432/gotrue_auth?search_path=auth
GOTRUE_JWT_SECRET=<random, min 32 chars>
GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOTRUE_EXTERNAL_GOOGLE_SECRET=<from Google Cloud Console>
```

Delete factory placeholder secrets with `$patch: delete`.

### 3. Patch GoTrue hostname and URLs

```yaml
# Ingress — real hostname
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gotrue-auth-ingress
spec:
  rules:
    - host: "secure.my-tenant.com"
```

```yaml
# Deployment — external URLs
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gotrue-auth
spec:
  template:
    spec:
      containers:
        - name: gotrue
          env:
            - name: API_EXTERNAL_URL
              value: "https://secure.my-tenant.com"
            - name: GOTRUE_SITE_URL
              value: "https://secure.my-tenant.com/landing"
            - name: GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI
              value: "https://secure.my-tenant.com/callback"
```

> **Note:** `GOTRUE_SITE_URL` points to `/landing` — the landing page served by authz that converts the OAuth token into a cookie and redirects the user to the original URL.

```yaml
# Ingress — route /landing to authz, everything else to GoTrue
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gotrue-auth-ingress
spec:
  rules:
    - host: "secure.my-tenant.com"
      http:
        paths:
          - path: /landing
            pathType: Exact
            backend:
              service:
                name: gotrue-authz
                port:
                  number: 8080
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gotrue-auth
                port:
                  number: 9999
```

### 4. Patch authz middleware address (FQDN)

The forwardAuth middleware needs a full DNS name to work cross-namespace:

```yaml
# Patch for Middleware gotrue-auth
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: gotrue-auth
spec:
  forwardAuth:
    address: "http://gotrue-authz.<namespace>.svc.cluster.local:8080/"
```

Replace `<namespace>` with the namespace where gotrue-auth is deployed (e.g., `security`).

### 5. Patch authz authorize URL

The authz service needs to know the public URL of GoTrue for login redirects:

```yaml
# Patch for Deployment gotrue-authz
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gotrue-authz
spec:
  template:
    spec:
      containers:
        - name: gotrue-authz
          env:
            - name: GOTRUE_AUTHORIZE_URL
              value: "https://secure.my-tenant.com"
```

### 6. Protect your apps

Add this annotation to any Ingress you want to protect:

```yaml
annotations:
  traefik.ingress.kubernetes.io/router.middlewares: <namespace>-gotrue-auth@kubernetescrd
```

Example: `security-gotrue-auth@kubernetescrd`

This works from **any namespace** — the middleware is a Traefik CRD with `allowCrossNamespace=true`.

### 7. Google OAuth — GCP setup

1. Go to **Google Cloud Console > APIs & Services > Credentials > Create OAuth client ID**
2. Application type: **Web application**
3. Authorized redirect URIs: `https://secure.my-tenant.com/callback`
4. Copy Client ID and Secret to `gotrue-secret`

## Per-app RBAC (optional)

By default, any user in the GoTrue database can access any protected app. To restrict per-app:

### Configure HOST_APP_MAP

```yaml
# Patch for ConfigMap gotrue-authz-config
apiVersion: v1
kind: ConfigMap
metadata:
  name: gotrue-authz-config
data:
  HOST_APP_MAP: '{"app1.my-tenant.com": "app1", "app2.my-tenant.com": "app2"}'
```

### Set user permissions

When creating users via the admin API, set `app_metadata.apps`:

```json
{"apps": ["app1", "app2"]}     // access to app1 and app2 only
{"apps": ["*"]}                 // access to everything
```

Users without the app in their list get a 403 Access Denied page.

## Custom landing and error pages (optional)

The authz service serves two HTML pages from the `gotrue-authz-config` ConfigMap:

| Key | Purpose | When shown |
|---|---|---|
| `landing.html` | Reads OAuth token from URL fragment, sets cookie, redirects to original URL | After Google/GitHub login |
| `error.html` | Access denied message | When user lacks permission for the app (403) |

To customize branding, patch the ConfigMap in your overlay:

```yaml
# Patch for ConfigMap gotrue-authz-config
apiVersion: v1
kind: ConfigMap
metadata:
  name: gotrue-authz-config
data:
  landing.html: |
    <!DOCTYPE html>
    <html>
    <head><title>Logging in...</title></head>
    <body>
      <p>Welcome to My Tenant! Logging you in...</p>
      <script>
        // IMPORTANT: keep the token-to-cookie logic from the default landing.html
        // Customize only the HTML/CSS around it
      </script>
    </body>
    </html>
  error.html: |
    <!DOCTYPE html>
    <html>
    <head><title>Access Denied</title></head>
    <body>
      <h1>Access Denied</h1>
      <p>Contact your administrator to request access.</p>
    </body>
    </html>
```

> **Important:** When customizing `landing.html`, keep the JavaScript logic that reads the token from the URL fragment, sets the `access_token` cookie, reads the `gotrue_redirect_to` cookie, and redirects. Only change the HTML/CSS around it.

## Additional OAuth providers

GoTrue supports 20+ OAuth providers. Enable them via env vars on the `gotrue-auth` deployment. Example for GitHub:

```yaml
# Patch for Deployment gotrue-auth
env:
  - name: GOTRUE_EXTERNAL_GITHUB_ENABLED
    value: "true"
  - name: GOTRUE_EXTERNAL_GITHUB_CLIENT_ID
    valueFrom:
      secretKeyRef:
        name: gotrue-secret
        key: GOTRUE_EXTERNAL_GITHUB_CLIENT_ID
  - name: GOTRUE_EXTERNAL_GITHUB_SECRET
    valueFrom:
      secretKeyRef:
        name: gotrue-secret
        key: GOTRUE_EXTERNAL_GITHUB_SECRET
  - name: GOTRUE_EXTERNAL_GITHUB_REDIRECT_URI
    value: "https://secure.my-tenant.com/callback"
```

Add the corresponding keys to `gotrue-secret`.

Other providers: Apple, Azure, Discord, GitLab, LinkedIn, Slack, Twitch, Twitter, etc. See [Supabase Auth docs](https://supabase.com/docs/guides/auth/social-login).

## User management

Signup is disabled by default (`GOTRUE_DISABLE_SIGNUP=true`) — the user DB is the allowlist.

### Create user

```bash
# Generate admin JWT (signed with GOTRUE_JWT_SECRET)
# Then:
curl -X POST https://secure.my-tenant.com/admin/users \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@company.com",
    "password": "<random>",
    "email_confirm": true,
    "app_metadata": {
      "provider": "google",
      "providers": ["google"],
      "apps": ["*"]
    }
  }'
```

A helper script is available at `scripts/gotrue-create-user.sh` in tenant overlays.

### List users

```bash
curl https://secure.my-tenant.com/admin/users \
  -H "Authorization: Bearer <admin-jwt>"
```

### Update user permissions

```bash
curl -X PUT https://secure.my-tenant.com/admin/users/<user-id> \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"app_metadata": {"apps": ["app1", "app2"]}}'
```

## Sharing GoTrue with AppFlowy

If the tenant already runs AppFlowy (which has its own GoTrue), the authz service can reuse it:

```yaml
# Patch gotrue-authz deployment
env:
  - name: GOTRUE_URL
    value: "http://appflowy-gotrue:9999"
```

## Environment variables reference

### gotrue-auth (GoTrue server)

| Env var | Description | Default |
|---|---|---|
| `API_EXTERNAL_URL` | Public URL of GoTrue | `https://auth.example.com` |
| `GOTRUE_SITE_URL` | Redirect target after OAuth callback (must point to `/landing`) | `https://auth.example.com/landing` |
| `GOTRUE_JWT_SECRET` | JWT signing secret (from secret) | — |
| `GOTRUE_JWT_EXP` | JWT expiration in seconds | `3600` |
| `GOTRUE_DISABLE_SIGNUP` | Disable self-registration | `true` |
| `GOTRUE_MAILER_AUTOCONFIRM` | Auto-confirm emails | `true` |
| `GOTRUE_EXTERNAL_GOOGLE_ENABLED` | Enable Google OAuth | `true` |
| `GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI` | Google callback URL | `https://auth.example.com/callback` |
| `DATABASE_URL` | Postgres connection (from secret) | — |

### gotrue-authz (validation service)

| Env var | Description | Default |
|---|---|---|
| `GOTRUE_URL` | Internal GoTrue URL for token validation | `http://gotrue-auth:9999` |
| `GOTRUE_AUTHORIZE_URL` | Public GoTrue URL for login redirects | same as `GOTRUE_URL` |
| `HOST_APP_MAP` | JSON: `{"hostname": "app-name"}` for per-app RBAC | `{}` (no RBAC) |
| `PORT` | Listen port | `8080` |

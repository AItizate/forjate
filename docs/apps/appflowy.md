# AppFlowy Cloud

AppFlowy is an open-source alternative to Notion — AI-powered collaborative workspace with wikis, project management, and databases.

- **Upstream repo:** https://github.com/AppFlowy-IO/AppFlowy-Cloud
- **License:** AGPL-3.0
- **Stack:** Rust (backend) + Flutter (client)

## Component location

**Path:** `k8s/components/apps/productivity/appflowy/`

### Sub-components included

| Sub-component | Description |
|---|---|
| `postgres/` | Dedicated PostgreSQL for AppFlowy Cloud |
| `gotrue/` | Authentication server (Supabase Auth fork) |
| `appflowy-cloud/` | Main AppFlowy Cloud server |

### External dependencies (add to tenant overlay)

```yaml
resources:
  - ../../components/apps/databases/redis   # required: pub/sub and cache
  # MinIO is already included in k8s/base as S3-compatible storage
```

## How to enable for a tenant

### 1. Add to overlay `kustomization.yaml`

```yaml
resources:
  - ../../base
  - ../../components/apps/databases/redis
  - ../../components/apps/productivity/appflowy
```

### 2. Patch the ingress hostname

```yaml
# patches/appflowy-ingress-patch.yaml
- op: replace
  path: /spec/rules/0/host
  value: appflowy.my-tenant.com
```

### 3. Patch the external URL

```yaml
# patches/appflowy-external-url-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: appflowy-cloud
spec:
  template:
    spec:
      containers:
        - name: appflowy-cloud
          env:
            - name: API_EXTERNAL_URL
              value: "https://appflowy.my-tenant.com"
```

### 4. Secret with real credentials

Create `secrets/appflowy.env` (use SealedSecret for production):

```env
DATABASE_URL=postgres://appflowy:REAL_PASSWORD@appflowy-postgres:5432/appflowy_cloud
GOTRUE_DATABASE_URL=postgres://appflowy:REAL_PASSWORD@appflowy-postgres:5432/appflowy_cloud
GOTRUE_JWT_SECRET=REAL_JWT_SECRET_MIN_32_CHARS
APPFLOWY_S3_ACCESS_KEY=REAL_MINIO_ACCESS_KEY
APPFLOWY_S3_SECRET_KEY=REAL_MINIO_SECRET_KEY
GOTRUE_SMTP_HOST=smtp.my-tenant.com
GOTRUE_SMTP_PORT=465
GOTRUE_SMTP_USER=noreply@my-tenant.com
GOTRUE_SMTP_PASS=REAL_SMTP_PASSWORD
GOTRUE_SMTP_ADMIN_EMAIL=admin@my-tenant.com
```

Also patch the postgres secret password to match `DATABASE_URL`.

## Architecture

```
AppFlowy Client
      │
      ▼
  Traefik (Ingress)
      │
      ▼
appflowy-cloud:8000
      │
      ├──► appflowy-gotrue:9999   (auth)
      ├──► appflowy-postgres:5432 (data)
      ├──► redis:6379             (pub/sub, cache)
      └──► minio:9000             (S3 storage — blobs, attachments)
```

## Key environment variables

| Variable | Description |
|---|---|
| `APPFLOWY_DATABASE_URL` | PostgreSQL connection string |
| `APPFLOWY_REDIS_URI` | Redis URI (default: `redis://redis:6379`) |
| `APPFLOWY_GOTRUE_BASE_URL` | Internal Gotrue URL |
| `APPFLOWY_S3_MINIO_URL` | MinIO URL (default: `http://minio:9000`) |
| `APPFLOWY_S3_BUCKET` | MinIO bucket (default: `appflowy`) |
| `APPFLOWY_ACCESS_CONTROL` | Enable access control (default: `true`) |

## Notes

- The AppFlowy desktop/mobile client connects via `https://appflowy.my-tenant.com`
- User registration: `GOTRUE_DISABLE_SIGNUP=false` (default). Set to `true` for private use.
- For production: use SealedSecrets for `appflowy-secret` and `appflowy-postgres-secret`
- MinIO must have the `appflowy` bucket created, or set `APPFLOWY_S3_CREATE_BUCKET=true`

# AFFiNE

AFFiNE is an open-source alternative to Notion + Miro — a knowledge base that combines docs, whiteboard, and databases in a single workspace. Local-first with real-time sync.

- **Upstream repo:** https://github.com/toeverything/AFFiNE
- **License:** MIT (Community Edition)
- **Stack:** TypeScript/Node.js (GraphQL server) + React (embedded frontend)

## Component location

**Path:** `k8s/components/apps/productivity/affine/`

### Sub-components included

| Sub-component | Description |
|---|---|
| `postgres/` | Dedicated PostgreSQL for AFFiNE (via OctoBase) |
| `affine/` | Main AFFiNE server (GraphQL API + embedded frontend) |

### External dependencies (add to tenant overlay)

```yaml
resources:
  - ../../components/apps/databases/redis   # required: cache and background jobs
  # MinIO is already included in k8s/base as S3-compatible storage
```

## How to enable for a tenant

### 1. Add to overlay `kustomization.yaml`

```yaml
resources:
  - ../../base
  - ../../components/apps/databases/redis
  - ../../components/apps/productivity/affine
```

### 2. Patch the ingress hostname

```yaml
# patches/affine-ingress-patch.yaml
- op: replace
  path: /spec/rules/0/host
  value: affine.my-tenant.com
```

### 3. Patch the external URL (required for correct link generation)

```yaml
# patches/affine-external-url-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: affine
spec:
  template:
    spec:
      containers:
        - name: affine
          env:
            - name: AFFINE_SERVER_EXTERNAL_URL
              value: "https://affine.my-tenant.com"
```

### 4. Secret with real credentials

Create `secrets/affine.env` (use SealedSecret for production):

```env
DATABASE_URL=postgres://affine:REAL_PASSWORD@affine-postgres:5432/affine
AFFINE_SERVER_APP_HINT=REAL_SECRET_32_CHARS_MIN
AFFINE_STORAGE_ACCESS_KEY=REAL_MINIO_ACCESS_KEY
AFFINE_STORAGE_SECRET_KEY=REAL_MINIO_SECRET_KEY
AFFINE_ADMIN_EMAIL=admin@my-tenant.com
AFFINE_ADMIN_PASSWORD=REAL_ADMIN_PASSWORD
MAILER_SENDER=noreply@my-tenant.com
MAILER_USER=user@smtp.com
MAILER_PASSWORD=REAL_SMTP_PASSWORD
MAILER_HOST=smtp.my-tenant.com
MAILER_PORT=465
```

Also patch the postgres secret password to match `DATABASE_URL`.

## Architecture

```
Browser / AFFiNE Client
      │
      ▼
  Traefik (Ingress)
      │
      ▼
  affine:3010  (GraphQL API + embedded frontend)
      │
      ├──► affine-postgres:5432  (data, documents, users)
      ├──► redis:6379            (cache, background jobs)
      └──► minio:9000            (S3 storage — blobs, files)
```

## Key environment variables

| Variable | Description |
|---|---|
| `AFFINE_SERVER_EXTERNAL_URL` | Public instance URL (required for correct link generation) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_SERVER_HOST` | Redis host (default: `redis`) |
| `AFFINE_STORAGE_PROVIDER` | Storage backend (`s3` for MinIO) |
| `AFFINE_STORAGE_ENDPOINT` | MinIO URL (default: `http://minio:9000`) |
| `AFFINE_STORAGE_BUCKET` | MinIO bucket (default: `affine`) |
| `AFFINE_STORAGE_FORCE_PATH_STYLE` | Required for MinIO (`true`) |
| `AFFINE_ADMIN_EMAIL` | Initial admin email |
| `AFFINE_ADMIN_PASSWORD` | Initial admin password |

## Notes

- Image used: `ghcr.io/toeverything/affine-graphql:stable` (use `canary` for bleeding edge)
- AFFiNE includes the frontend embedded — no separate UI deployment needed
- For production: use SealedSecrets for `affine-secret` and `affine-postgres-secret`
- MinIO must have the `affine` bucket created (create manually or via MinIO hook)
- PVC `pvc-affine-data` stores local data at `/root/.affine` (config, temp uploads)
- `AFFINE_SERVER_APP_HINT` is the app session signing secret — must be random and long

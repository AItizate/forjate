# CI Write-Back Integration

Este documento explica cómo integrar los repositorios de aplicaciones (como `my-app`) con el **Forjate** para automatizar actualizaciones de tags de imagen.

## Overview

El workflow `sync-app-image.yml` escucha eventos de tipo `app-image-updated` y actualiza automáticamente el tag de imagen en el overlay del tenant, luego hace push a la rama `develop`.

## Flujo de integración

```
my-app repo                  forjate repo
    (build)                              (listen)
      |                                    |
      ├─ Push build completed             |
      ├─ Trigger webhook ─────────────────┤
      |                              sync-app-image.yml
      |                                    |
      |                        ┌─ Update kustomization.yaml
      |                        ├─ Validate kustomize
      |                        ├─ Commit & Push to develop
      |                        └─ ArgoCD syncs automáticamente
      |
      └─ Continúa con deployment
```

## Configuración

### 1. Crear token de write-back en forjate

En GitHub, ve a:
- **Settings → Developer settings → Personal access tokens → Tokens (classic)**
- **Generate new token**
  - **Name**: `iac-write-back`
  - **Scopes**:
    - ✅ `repo` (full control of private repos)
    - ✅ `workflow` (update GitHub workflows)
  - **Expiration**: 90 días (o según tu política)

### 2. Agregar el token como secret en cada repo de app

En cada repo de aplicación (ej: `my-app`):
- **Settings → Secrets and variables → Actions**
- **New repository secret**
  - **Name**: `IAC_FACTORY_TOKEN`
  - **Value**: (pega el PAT generado en paso 1)

## Ejemplo: Workflow en my-app

Agrega este workflow a tu repo de aplicación:

```yaml
# .github/workflows/update-iac-factory.yml
name: Update IaC Factory

on:
  push:
    branches: [main, release/*]
  workflow_dispatch:  # Permite disparo manual

jobs:
  build-and-notify:
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ steps.meta.outputs.tag }}
    steps:
      - uses: actions/checkout@v3

      - name: Set image tag
        id: meta
        run: |
          # Opción A: Usar commit SHA
          TAG="${{ github.sha }}"

          # Opción B: Usar fecha + SHA (más legible)
          # TAG="$(date +%Y%m%d)-${{ github.sha }}"

          # Opción C: Usar git tag/release version
          # TAG=$(git describe --tags --always)

          echo "tag=${TAG}" >> $GITHUB_OUTPUT
          echo "Image tag: ${TAG}"

      - name: Build and push image
        run: |
          # Tu lógica de build/push
          # docker build -t my-app:${{ steps.meta.outputs.tag }} .
          # docker push my-app:${{ steps.meta.outputs.tag }}
          echo "Built and pushed image: my-app:${{ steps.meta.outputs.tag }}"

  notify-iac-factory:
    needs: build-and-notify
    runs-on: ubuntu-latest
    steps:
      - name: Trigger IaC Factory update
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.IAC_FACTORY_TOKEN }}" \
            -H "Accept: application/vnd.github.v3+json" \
            https://api.github.com/repos/your-org/forjate/dispatches \
            -d '{
              "event_type": "app-image-updated",
              "client_payload": {
                "app_name": "my-app",
                "new_tag": "${{ needs.build-and-notify.outputs.image-tag }}",
                "tenant": "my-tenant",
                "namespace": "default",
                "trigger_url": "${{ github.server_url }}/${{ github.repository }}/commit/${{ github.sha }}"
              }
            }'
```

## Payload del evento

El workflow espera un `repository_dispatch` con este `client_payload`:

```json
{
  "app_name": "my-app",           // Nombre de la app (usado para buscar en kustomization.yaml)
  "new_tag": "abc123def",              // Nuevo tag/SHA de la imagen
  "tenant": "my-tenant",            // [Opcional] Tenant a actualizar (default: my-tenant)
  "namespace": "default",              // [Opcional] Namespace (para referencia, no se usa aún)
  "trigger_url": "https://github..."   // [Opcional] URL del commit que dispara la actualización
}
```

## Requerimientos

### En forjate:

- ✅ `.github/workflows/sync-app-image.yml` creado
- ✅ Secret `IAC_WRITE_BACK_TOKEN` configurado
- ✅ Rama `develop` protegida (opcional, pero recomendado para CI/CD seguro)

### En cada repo de app:

- ✅ Secret `IAC_FACTORY_TOKEN` configurado
- ✅ Workflow que dispara `repository_dispatch` con `event_type: "app-image-updated"`

### En kustomization.yaml del tenant:

El tag debe estar en un formato que el sed pueda buscar:

```yaml
# ✅ VÁLIDO - El workflow puede actualizar esto
patches:
  - path: patches/image-patch.yaml

# O en un resource:
resources:
  - deployment.yaml  # que contiene: image: my-app:v1.0.0
```

## Validación

Para probar el workflow manualmente:

```bash
curl -X POST \
  -H "Authorization: token YOUR_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/your-org/forjate/dispatches \
  -d '{
    "event_type": "app-image-updated",
    "client_payload": {
      "app_name": "my-app",
      "new_tag": "test-tag-123",
      "tenant": "my-tenant"
    }
  }'
```

Luego chequea el workflow en:
- GitHub → **Actions → Sync App Image Tag**

## Troubleshooting

### El workflow no se dispara

1. Verifica que el `event_type` sea exactamente `app-image-updated`
2. Verifica que el token `IAC_FACTORY_TOKEN` sea válido y tenga permisos `repo` y `workflow`
3. Chequea que el repo de origen tiene permisos para disparar eventos en el repo destino

### El workflow falla en validación de Kustomize

1. Verifica que el path en `client_payload.tenant` existe: `k8s/overlays/{tenant}`
2. Ejecuta localmente: `kustomize build k8s/overlays/my-tenant`
3. Verifica que el patrón del app_name coincida en kustomization.yaml

### Los cambios no se pushean

1. Verifica que el token tiene permisos de `write` en el repo
2. Verifica permisos de rama: ¿`develop` está protegida sin permitir pushes automáticos?
3. Chequea que el `git.user.name` y `git.user.email` estén configurados

## Seguridad

- 🔐 Usa un token específico (no reutilices el de ArgoCD)
- 🔐 Limita permisos del token (solo `repo` y `workflow`)
- 🔐 Establece expiración en el token (90 días recomendado)
- 🔐 Rota tokens periódicamente
- ✅ Valida que la estructura de kustomize sea correcta antes de pushear
- ✅ Los commits van con user `iac-sync@bot.local` para identificar cambios automáticos

## Próximos pasos

- [ ] Crear token `IAC_FACTORY_TOKEN` en GitHub
- [ ] Agregar secret en cada repo de app
- [ ] Crear workflow en my-app (u otras apps)
- [ ] Testear disparo manual
- [ ] Validar que ArgoCD sincroniza correctamente con los cambios

---

Para más información sobre la estructura del IaC Factory, ver [`../CONTRIBUTING.md`](../CONTRIBUTING.md) y [`../CLAUDE.md`](../CLAUDE.md).

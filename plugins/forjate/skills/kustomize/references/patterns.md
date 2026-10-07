# Recurring patterns

## Resource sizing for a laptop (Crawl)

```yaml
# patches/postgres-resources.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  template:
    spec:
      containers:
        - name: postgres
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits: { cpu: "1", memory: 1Gi }
```

Registered with a `target` so the patch applies regardless of file order:

```yaml
patches:
  - path: patches/postgres-resources.yaml
    target: { kind: StatefulSet, name: postgres }
```

## Secrets a component expects

```yaml
secretGenerator:
  - name: postgres-secret            # exact name the component mounts
    envs: [secrets/postgres.env]     # gitignored; secrets/postgres.env.example is committed
    options: { disableNameSuffixHash: true }
```

`secrets/postgres.env.example`:

```
POSTGRES_DB=app
POSTGRES_USER=app
POSTGRES_PASSWORD=change-me
```

## Lifecycle Job (suspended, cleaned up)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: <prefix>-validate
spec:
  suspend: true                      # the runner un-suspends in order
  backoffLimit: 0
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: Never
      securityContext: { runAsNonRoot: true, runAsUser: 1000, seccompProfile: { type: RuntimeDefault } }
      containers:
        - name: validate
          image: postgres:16
          command: ["sh", "-c", "psql \"$DATABASE_URL\" -c 'select count(*) from customers' | grep -q 2000000"]
          envFrom: [{ secretRef: { name: postgres-secret } }]
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: [ALL] } }
          resources: { requests: { cpu: 50m, memory: 64Mi }, limits: { cpu: 500m, memory: 256Mi } }
```

In-cluster DNS for an endpoint declared in `usecase.yaml`: `<service>.uc-<name>.svc.cluster.local:<port>`.

## Hostname patch for an Ingress

```yaml
- op: replace
  path: /spec/rules/0/host
  value: app.uc-<name>.example.com
```

```yaml
patches:
  - path: patches/app-host.yaml
    target: { kind: Ingress, name: app }
```

## PSA label on the namespace (Walk and Run)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: uc-<name>
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

## Mounting a component into a different namespace

Components carry no namespace. The sub-overlay's `namespace:` field places everything it lists. If a component must live elsewhere (LiteLLM in `ai-tools`, say), give it its own `namespaces/<ns>/kustomization.yaml` and compose both from the root.

## Shape of a tenant root (remote pattern)

Observed in `im-u/iac`, a production tenant (`docs/use-case-builder/tenant-patterns.md`): there is no `base/` + `overlays/` split in a tenant. One root pulls the factory base remotely and composes namespace children; a root label identifies the overlay on every resource.

```yaml
# k8s/kustomization.yaml of a tenant
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=v1.1.0
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/sealed-secrets?ref=v1.1.0
  - ./namespaces/default
  - ./namespaces/security
labels:
  - pairs:
      app.kubernetes.io/managed-by: kustomize
      app.kubernetes.io/overlay: <tenant>
```

`k8s/patches/` holds cross-namespace infra patches; `k8s/namespaces/<ns>/` holds `kustomization.yaml` plus `patches/`, `secrets/`, `configs/`, `middlewares/`. A sub-overlay sets `namespace: <ns>` (the root never does). A use case graduating into a tenant lands as one `namespaces/uc-<name>/` child of that root.

## Remote references: both URL forms, always pinned

Two shapes coexist and both need `?ref=<tag>`:

```yaml
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/databases/postgres?ref=v1.1.0   # subdirectory of the factory: double slash
  - ssh://git@github.com/<org>/<app>.git/k8s/base?ref=v0.4.0                                       # root path of a sibling app repo: single slash
```

A branch ref (`?ref=develop`, `?ref=main`, `?ref=feat/...`) is drift: two builds of the same commit can differ. Observed: five factory versions and three branches in one tenant tree. From Walk every ref is a tag; `remote_refs: mixed` in the devops record is the honest state until a `ci` check (`ref-pinning-check`) finds no branch.

Each resource entry is one SSH clone per ArgoCD refresh: prefer `bundles/temporal-stack` over `apps/workflows/temporal` + `apps/databases/postgres` when they land in one namespace (`# single bundle = 1 SSH clone`, as the tenant comments it).

## Replacing a placeholder Secret with a SealedSecret

Catalog components ship a placeholder Secret under the name they mount. From Walk the overlay deletes it and supplies a SealedSecret of the same name; the most repeated patch in the surveyed tenant (11 times):

```yaml
patches:
  - target: { kind: Secret, name: postgres-secret }
    patch: |
      $patch: delete
      apiVersion: v1
      kind: Secret
      metadata:
        name: postgres-secret
resources:
  - secrets/sealed-postgres-secret.yaml      # metadata.name == postgres-secret; namespace repeated in spec.template.metadata
```

Next to it, `secrets/postgres-secret.env.example` with the header the security skill requires (`# To generate:`, `# To seal:`), so the recipe travels with the secret. `sealedsecrets.bitnami.com/cluster-wide: "true"` only on the registry pull secret.

## Patch files: naming and registration

`patches/<app>-<concern>-patch.yaml` registered by `path` + `target`:

```yaml
patches:
  - path: patches/postgres-storage-patch.yaml
    target: { kind: StatefulSet, name: postgres }
  - path: patches/agent-host-patch.yaml
    target: { kind: Ingress, name: agent }
```

Inline `patch: |` is reserved for `$patch: delete` and JSON6902 operations of three lines or fewer. Recurring concerns: `host` (replace `/spec/rules/0/host`, or a full strategic-merge Ingress for several hosts), `storage` (`/spec/volumeClaimTemplates/0/spec/storageClassName`), `resources`, `replicas` (`replicas: 0` carries `# Temporarily scaled to 0 — <reason>`), `nodeselector` (a tenant label such as `<tenant>/cpu-arch`, with the image downgrade it forces and the reason), `pullsecret` (`target: {kind: ServiceAccount}` with no name, so every ServiceAccount gets `imagePullSecrets`), `middleware` (Traefik annotation with `~1` escaping in the JSON pointer), `namespace` (`labelSelector` targeting, e.g. `app.kubernetes.io/part-of=zitadel-stack`, to force `metadata.namespace` onto Helm-rendered output).

## Index-based JSON6902 into `env` arrays

The main breakage point on upgrades in the surveyed tenant. Prefer a strategic merge keyed on `name`:

```yaml
# patches/app-env-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: app }
spec:
  template:
    spec:
      initContainers:
        - name: init-db
          env:
            - { name: DB_HOST, value: postgres }   # merged by name, order-independent
```

When an index is unavoidable (an upstream list without `name`), every op carries a comment naming the ordering it assumes:

```yaml
  - target: { kind: Deployment, name: app }
    patch: |
      # assumes initContainers[0] is init-db and its env[3] is DB_HOST (upstream v2.4)
      - op: replace
        path: /spec/template/spec/initContainers/0/env/3/value
        value: postgres
```

## NetworkPolicy default-deny (Walk and Run)

Generated from the security record's `network_policy: default-deny` and `egress_allowlist` (external hostnames) plus the in-cluster allows you derive from the architecture record's workloads and the components in the overlay; not optional, not a component. Absent from a whole production tenant because the convention listed it as hardening. A per-workload matrix is written only when the security record says `egress_matrix: required`.

```yaml
# netpol-default-deny.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny, namespace: uc-<name> }
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-dns, namespace: uc-<name> }
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to: [{ namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } } }]
      ports: [{ protocol: UDP, port: 53 }, { protocol: TCP, port: 53 }]
---
# one per in-cluster dependency you derive (workload → component), e.g. agent-api → postgres; and one per external hostname in egress_allowlist
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-agent-api-to-postgres, namespace: uc-<name> }
spec:
  podSelector: { matchLabels: { app: agent-api } }
  policyTypes: [Egress]
  egress:
    - to: [{ podSelector: { matchLabels: { app: postgres } } }]
      ports: [{ protocol: TCP, port: 5432 }]
```

External destinations (`worker: odoo.example.com:443`) become an `ipBlock` or a FQDN policy depending on the CNI; say which in the overlay README. Ingress to exposed surfaces is allowed from the ingress controller's namespace only.

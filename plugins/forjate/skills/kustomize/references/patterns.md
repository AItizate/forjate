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

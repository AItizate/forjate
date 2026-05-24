# `cluster-introspector`

> A read-only agent that observes its own cluster.

A small Deployment + ServiceAccount + read-only ClusterRole that lets an agent (OpenClaw-based by default, but the image is interchangeable) inspect the live state of the cluster it runs in — pods, services, configmaps, deployments, jobs, ingresses, RBAC, storage, metrics — without the ability to mutate anything.

## What it includes

- A `ServiceAccount` named `cluster-introspector`
- A `ClusterRole` of the same name granting `get / list / watch` (and `get / list` for RBAC) across the common API groups
- A `ClusterRoleBinding` linking the SA to the role
- A `Deployment` with an OpenClaw-compatible container shape (PVC for workspace, optional config secret, port `18789`)
- A `Service` exposing the agent's HTTP port

## Why a read-only role

The point is observability for an agent that needs to reason about the cluster — answer questions like _"which deployments don't have liveness probes?"_, _"what's churning pods?"_, _"who has cluster-admin bound?"_ — without ever being able to write. A separate component (or a deliberate overlay) is required if you want write capabilities, on purpose.

## Using it in an overlay

```yaml
# overlay/kustomization.yaml
resources:
  - ../../base
  - ../../components/apps/agents/cluster-introspector

# Patch the ClusterRoleBinding to point at the namespace where the SA lives:
patches:
  - target:
      kind: ClusterRoleBinding
      name: cluster-introspector
    patch: |-
      - op: replace
        path: /subjects/0/namespace
        value: home

# Replace the placeholder image and provide config (optional):
  - target:
      kind: Deployment
      name: cluster-introspector
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/image
        value: ghcr.io/myorg/my-introspector:v1.2.3
```

## Container contract

The default image path is `ghcr.io/example/cluster-introspector:latest` — replace it with your own. The container is expected to:

- Use the in-cluster ServiceAccount token (`/var/run/secrets/kubernetes.io/serviceaccount/`) to authenticate against the Kubernetes API
- Read optional configuration from `/etc/agent/` (mounted from the `cluster-introspector-config` Secret, optional)
- Persist its workspace under `/home/node/.openclaw` (PVC)
- Expose HTTP on port `18789`

If you publish an OSS image that satisfies that contract (an OpenClaw distribution wired for cluster introspection), point this component at it.

## Security notes

- The role is broad but read-only. Bind it only to the SA in this component. Do NOT add other subjects.
- The agent can read Secret **names** via configmaps/pods, but not Secret **values** — `secrets` is intentionally not in the rules.
- If your cluster runs PSA (Pod Security Admission), this component runs as a non-root user (UID 1000) and does not need elevated capabilities.

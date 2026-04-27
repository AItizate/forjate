# ArgoCD

**Official Website:** [https://argo-cd.readthedocs.io/](https://argo-cd.readthedocs.io/)

## Purpose in Architecture

`ArgoCD` is a **declarative, GitOps continuous delivery tool for Kubernetes**. In our infrastructure, it serves as the **GitOps Controller** that automatically synchronizes the desired state defined in Git repositories with the actual state of Kubernetes clusters.

It is the "automation engine" that ensures our infrastructure remains consistent with the configurations stored in this repository.

## Basic Operation

- **Git-Based Source of Truth:** ArgoCD monitors Git repositories containing Kubernetes manifests and automatically applies changes when the repository is updated.
- **Application Management:** It manages `Application` resources that define what should be deployed, where it should be deployed, and how it should be synchronized.
- **Automatic Synchronization:** ArgoCD continuously compares the live state in the cluster with the desired state in Git and can automatically sync differences.
- **Health Monitoring:** It provides real-time visibility into the health and sync status of all managed applications.
- **Rollback Capabilities:** ArgoCD maintains a history of deployments and allows easy rollbacks to previous versions.

## Key Features

- **Kustomize Integration:** Native support for Kustomize, allowing it to work seamlessly with our base/overlay structure.
- **Multi-Cluster Management:** Can manage applications across multiple Kubernetes clusters from a single control plane.
- **RBAC Integration:** Fine-grained access control that can integrate with existing authentication systems.
- **Web UI and CLI:** Provides both a web interface and command-line tools for management and monitoring.
- **Webhook Support:** Can trigger synchronization based on Git webhooks for faster deployment cycles.

## Project Integration

- **Base Configuration:** The base ArgoCD installation is located in `k8s/components/apps/continuous-delivery/argocd/`, which includes:
  - Official ArgoCD manifests from the stable release
  - Generic ingress configuration for web UI access
  - Common labels and namespace configuration

- **Namespace:** ArgoCD runs in its dedicated `argocd` namespace, defined in `k8s/components/apps/continuous-delivery/argocd/namespace.yaml`.

- **GitOps Workflow:** ArgoCD enables our GitOps workflow by:
  - Monitoring this repository for changes
  - Automatically applying updates to tenant overlays
  - Providing visibility into deployment status across all environments

- **Tenant Management:** Each tenant overlay can define ArgoCD `Application` resources that:
  - Point to specific paths in this repository
  - Configure environment-specific parameters
  - Enable automatic or manual synchronization policies

## Usage with Kustomize

ArgoCD has excellent integration with Kustomize, supporting:

- **Overlay-based Deployments:** Can deploy different overlays to different clusters
- **Dynamic Configuration:** Supports Kustomize patches, components, and generators
- **Parameter Overrides:** Can override Kustomize parameters directly in the Application spec
- **Build Options:** Configurable Kustomize build options for advanced use cases

Example Application configuration for a tenant:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tenant-infrastructure
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/forjate.git
    targetRevision: HEAD
    path: k8s/overlays/your-tenant
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## Security Considerations

- **RBAC:** ArgoCD includes comprehensive RBAC controls for managing access to applications and clusters
- **Secret Management:** Integrates with Kubernetes secrets and external secret management systems
- **Network Security:** Can be configured with ingress controllers and authentication proxies
- **Audit Logging:** Provides detailed audit logs of all deployment activities

## Integration with Our Stack

ArgoCD complements our existing infrastructure by:

- **Working with Traefik:** Uses our Traefik ingress controller for web UI access
- **Certificate Management:** Leverages cert-manager for TLS certificates
- **Authentication:** Can integrate with oauth2-proxy for centralized authentication
- **Monitoring:** Provides metrics that can be scraped by Prometheus/Grafana

## References

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [ArgoCD Kustomize Integration](https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/)
- [GitOps Principles](https://opengitops.dev/)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [ArgoCD Operator Manual](https://argo-cd.readthedocs.io/en/stable/operator-manual/)

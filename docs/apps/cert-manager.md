# Cert-Manager

**Official Website:** [https://cert-manager.io/](https://cert-manager.io/)

## Purpose in Architecture

`cert-manager` is a fundamental component in our Kubernetes cluster that automates the management and issuance of TLS certificates from various sources, such as Let's Encrypt. Its role is to ensure that communications with our services exposed via Ingress are secure (HTTPS).

## Basic Operation

1.  **Observes Ingresses:** `cert-manager` monitors `Ingress` objects in the cluster.
2.  **Requests Certificates:** When an Ingress includes a `tls` section, `cert-manager` realizes it needs a certificate for the specified host.
3.  **Solves Challenges:** It communicates with the configured certificate authority (CA) (e.g., Let's Encrypt) to request a certificate. It automatically completes domain validation challenges (HTTP-01 or DNS-01) to prove that we control the domain.
4.  **Stores the Certificate:** Once issued, the certificate and its private key are stored in a Kubernetes `Secret`.
5.  **Associates with Ingress:** The Ingress Controller (in our case, [Traefik](./traefik.md)) uses this `Secret` to terminate the TLS connection, enabling HTTPS.

## Project Integration

-   The base configuration for `cert-manager` is located in `k8s/base/apps/cert-manager/`.
-   The `Issuers` or `ClusterIssuers` (which define where to obtain certificates from) are configured in the `overlays`, as they depend on the environment (e.g., Let's Encrypt's `staging` is used for development and `production` for `my-tenant`).

Thanks to `cert-manager`, all exposed applications, such as `open-webui` or `kubernetes-dashboard`, can be served securely over HTTPS without manual intervention.

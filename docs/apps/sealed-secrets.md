# Sealed Secrets

**Official Website:** [https://github.com/bitnami-labs/sealed-secrets](https://github.com/bitnami-labs/sealed-secrets)

## Purpose in Architecture

`Sealed Secrets` is a **Kubernetes controller and tool for one-way encrypted secrets**. In our infrastructure, it allows us to store secrets safely in a public Git repository. The secrets are encrypted into a `SealedSecret` custom resource, which can only be decrypted by the controller running in the target Kubernetes cluster.

This approach enables us to manage secrets declaratively and align them with our GitOps workflow, ensuring that even sensitive information is version-controlled without exposing it.

## Basic Operation

- **Asymmetric Encryption:** The controller generates a public-private key pair. The private key remains in the cluster, while the public key is used by the `kubeseal` CLI tool to encrypt secrets.
- **Client-Side Encryption:** Developers use the `kubeseal` CLI to convert standard Kubernetes `Secret` manifests into `SealedSecret` manifests.
- **Server-Side Decryption:** The Sealed Secrets controller, running in the cluster, detects new `SealedSecret` resources, decrypts them using its private key, and creates a standard Kubernetes `Secret` that workloads can use.
- **Scope:** Sealed Secrets are scoped to the namespace and name of the original secret. They cannot be used in a different namespace or with a different name.

## Creating Sealed Secrets

You can create `SealedSecret` resources from literals, `.env` files, or existing `Secret` YAML files.

### 1. From Literals

This is the most direct way to create a secret from the command line.

**Command:**
```bash
kubectl create secret generic <secret-name> \
  --from-literal=<key1>=<value1> \
  --from-literal=<key2>=<value2> \
  --dry-run=client -o yaml | kubeseal --format yaml > <sealed-secret-filename>.yaml
```

**Example:**
```bash
kubectl create secret generic my-db-credentials \
  --from-literal=username=admin \
  --from-literal=password='s3cr3tP@ssw0rd!' \
  --dry-run=client -o yaml | kubeseal --format yaml > my-db-credentials.sealed.yaml
```

### 2. From an `.env` File

This method is useful for managing multiple key-value pairs stored in a standard `.env` file.

**Example `.env` file (`db-credentials.env`):**
```
DB_USER=admin
DB_PASSWORD=supersecret
```

**Command:**
```bash
kubectl create secret generic my-db-credentials \
  --from-env-file=db-credentials.env \
  --dry-run=client -o yaml | kubeseal --format yaml > my-db-credentials.sealed.yaml
```

### 3. From an Existing Secret YAML File

If you already have a standard `Secret` manifest, you can pipe it directly to `kubeseal`. This is also the principle behind the `scripts/convert-to-sealed-secret.sh` script in this repository.

**Example `Secret` file (`my-secret.yaml`):**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-api-keys
type: Opaque
data:
  apiKey: MWYyZDFlMmU2N2Rm
  apiSecret: ZjM0YjVlN2YzMTc0
```
*(Note: `data` values must be Base64 encoded)*

**Command:**
```bash
kubeseal --format yaml < my-secret.yaml > my-api-keys.sealed.yaml
```

## Project Integration

- **GitOps Workflow:** Sealed Secrets are fundamental to our GitOps workflow. Encrypted secrets are committed to the repository and synchronized by ArgoCD. The controller in the cluster then converts them back into usable `Secret` resources.
- **Secret Storage:** All tenant-specific sealed secrets should be stored in the `k8s/overlays/<tenant-name>/secrets/` directory.
- **Automation:** The `scripts/convert-to-sealed-secret.sh` script provides a convenient wrapper for converting existing `Secret` manifests into `SealedSecret` resources.

## Security Considerations

- **Private Key Backup:** The private key used by the controller is critical. If lost, all `SealedSecret` resources in the repository become undecipherable. It is stored in a Kubernetes secret named `sealed-secrets-key` in the controller's namespace and should be backed up.
- **RBAC:** Access to the private key secret should be strictly limited using Kubernetes RBAC.
- **Public Key:** The public key is safe to share and is used by `kubeseal` for encryption. You can fetch it by running: `kubeseal --fetch-cert`.

## References

- [Sealed Secrets Official Documentation](https://github.com/bitnami-labs/sealed-secrets)
- [Bitnami Blog: A Guide to Kubernetes Secrets](https://bitnami.com/blog/a-guide-to-kubernetes-secrets-with-sealed-secrets/)
- [GitOps Principles](https://opengitops.dev/)

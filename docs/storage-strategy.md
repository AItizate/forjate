# IaC Storage Strategy: A Component-Based Approach

This document outlines the standardized strategy for managing `PersistentVolumes` (PVs) and `PersistentVolumeClaims` (PVCs) within the forjate repository. The goal is to create a flexible, scalable, and DRY (Don't Repeat Yourself) system using Kustomize Components.

## Core Philosophy: Requests vs. Offers

We decouple the **request** for storage from the **offer** of storage.

- **Storage Request (PVC):** An application in the `base` layer declares that it *needs* persistent storage. It defines a `PersistentVolumeClaim` specifying *what* it needs (e.g., 5Gi of space, `ReadWriteOnce` access). It should **not** specify *how* that need is met.
- **Storage Offer (PV):** The underlying environment *offers* a way to provide storage. This is a `PersistentVolume` that specifies *how* storage is provided (e.g., via a local `hostPath`, an NFS share, or a cloud provider's block storage like AWS EBS).

The Kustomize `overlay` for a specific environment is responsible for matching the requests from applications with the offers available in that environment.

## The "Components" Pattern

To implement this, we use the `components` feature in Kustomize. A component is a reusable, pre-packaged unit of Kubernetes configuration.

### Directory Structure

Our storage components reside in `k8s/components/pvs/`. Each subdirectory represents a different *type* of storage "offer":

```
k8s/components/pvs/
├── local-storage/      # For local development (e.g., k3d)
│   ├── kustomization.yaml
│   └── pv.yaml         # A generic local PV definition
└── nfs-storage/        # For on-premise or NFS-backed environments
    ├── kustomization.yaml
    └── pv.yaml         # A generic NFS PV definition
```

- **Application (`k8s/base/apps/<app-name>/`):**
  - Contains a `pvc.yaml`. This file is the "request". It **must not** contain a `storageClassName` or `selector`.
  - The `kustomization.yaml` for the app only references its own resources, including the `pvc.yaml`. It does not know about the PV.

- **Overlay (`k8s/overlays/<env-name>/`):**
  - The `kustomization.yaml` in the overlay assembles the final configuration.

### Example Overlay Workflow (`dev` environment)

Here is how the `k8s/overlays/dev/kustomization.yaml` brings everything together:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

# 1. Include desired applications (which contain the PVC "requests")
resources:
  - ../../base/namespaces/automation
  - ../../base/namespaces/ai

# 2. Include the storage "offer" for this environment
components:
  - ../../components/pvs/local-path

# 3. Configure the generic offer and requests for this specific environment
patches:
  # Patch A: Configure the generic local PV component
  - patch: |-
      - op: replace
        path: /metadata/name
        value: pv-node-red-dev-volume
      - op: replace
        path: /spec/local/path
        value: /tmp/k3d-volumes/node-red
    target:
      kind: PersistentVolume
      # This target needs to be specific enough to select the correct PV
      # if multiple PVs are included from components.

  # Patch B: Tell all PVCs to use the 'local-path' storage class
  - path: patches/storageclass-patch.yaml
    target:
      kind: PersistentVolumeClaim
```

### How it Works in Practice

1.  **Request:** The `node-red` application base includes a PVC asking for storage.
2.  **Assembly:** The `dev` overlay's kustomization includes `node-red` (the request) and `local-path` (the offer).
3.  **Configuration:**
    - A patch targets the generic `PersistentVolume` from the `local-path` component and gives it a unique name and a specific `path` for the dev environment.
    - A second patch targets all `PersistentVolumeClaim` resources being deployed and sets their `storageClassName` to `local-path`, which is the provisioner available in the `k3d` dev environment.

### Benefits of this Strategy

- **DRY:** The definition for a type of storage (NFS, local, etc.) exists in only one place.
- **Simplicity:** Application definitions are clean and only care about their own needs. Overlays become a high-level manifest of which components and apps to deploy.
- **Scalability:** To support a new storage backend (e.g., Google Cloud Storage), you simply add a new component in `k8s/components/pvs/`. No existing applications or overlays need to be changed.
- **Clarity:** It's immediately clear from an overlay's `kustomization.yaml` what kind of storage it provides and which applications it deploys.

---

### Alternative: A Simpler, Direct Approach

While the component-based pattern is the recommended ideal for maximum clarity and reusability, some overlays may use a more direct approach for simplicity.

In this alternative, the overlay **does not** include a storage component from `k8s/components/pvs/`. Instead, it relies on a `StorageClass` that is assumed to already exist in the target Kubernetes cluster.

**How it Works:**

1.  **No `components`:** The overlay's `kustomization.yaml` omits the `components` section for storage.
2.  **Global Patch:** It uses a patch to set the `storageClassName` on all `PersistentVolumeClaims` to the name of the pre-existing `StorageClass` (e.g., `local-path`, `longhorn`).

The `my-tenant` overlay is an example of this approach. It uses `patches/storageclass-patch.yaml` to set the `storageClassName` to `local-path`, depending on the `local-path-provisioner` being installed and configured in the cluster beforehand. This method is faster to implement but makes the overlay less self-contained.

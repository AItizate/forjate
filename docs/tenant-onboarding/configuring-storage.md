# Configuring Persistent Storage for a New Tenant

A critical aspect of tenant configuration is providing persistent storage for stateful applications. Our platform uses a flexible, `StorageClass`-based approach to handle this.

## The Strategy: `StorageClass` and Patches

Instead of creating `PersistentVolumes` (PVs) manually, we use **dynamic provisioning**. The process works as follows:

1.  **Applications request storage**: An application manifest contains a `PersistentVolumeClaim` (PVC), which is a request for storage of a certain size.
2.  **The PVC specifies a `StorageClass`**: The PVC has a `storageClassName` field that tells Kubernetes *what kind* of storage it needs.
3.  **The `StorageClass` defines the provider**: The `StorageClass` resource itself points to a provisioner (e.g., Longhorn, NFS, GCP Persistent Disk) that knows how to create the physical storage.
4.  **A global patch sets the `storageClassName`**: We use a Kustomize patch in each tenant overlay to set the appropriate `storageClassName` on all PVCs for that tenant.

This approach decouples our applications from the underlying storage technology, making the platform portable and flexible.

## Configuration Steps

### 1. Choose a Storage Backend

Determine the storage backend available in your target cluster.
*   **For Longhorn-enabled clusters** (like `my-tenant`): You can use the default `longhorn` `StorageClass`.
*   **For NFS-based clusters** (like `my-home-tenant`): You need to define a `StorageClass` that points to your NFS CSI driver.

### 2. Configure the Tenant Overlay

#### For a Longhorn Backend:

1.  **Create a Patch**: Create the file `k8s/overlays/{tenant-name}/patches/storageclass-patch.yaml` with the following content:
    ```yaml
    # This patch sets the storageClassName for all PersistentVolumeClaims.
    - op: add
      path: /spec/storageClassName
      value: longhorn
    ```
2.  **Update `kustomization.yaml`**: Ensure the tenant's `kustomization.yaml` applies this patch to all PVCs:
    ```yaml
    patches:
      - path: patches/storageclass-patch.yaml
        target:
          kind: PersistentVolumeClaim
    ```

#### For an NFS Backend:

1.  **Create a `StorageClass` Manifest**: Create `k8s/overlays/{tenant-name}/storage/nfs-storageclass.yaml`:
    ```yaml
    # k8s/overlays/{tenant-name}/storage/nfs-storageclass.yaml
    apiVersion: storage.k8s.io/v1
    kind: StorageClass
    metadata:
      name: nfs-tenant # You can name this as you wish
    provisioner: nfs.csi.k8s.io # Make sure this matches your installed CSI driver
    parameters:
      server: "YOUR_NFS_SERVER_IP_OR_HOSTNAME"
      share: "/path/to/your/nfs/share"
    reclaimPolicy: Retain
    volumeBindingMode: Immediate
    ```
    **Remember to replace the `server` and `share` parameters.**

2.  **Create a Patch**: Create `k8s/overlays/{tenant-name}/patches/storageclass-patch.yaml` pointing to your new `StorageClass`:
    ```yaml
    # This patch sets the storageClassName for all PersistentVolumeClaims.
    - op: add
      path: /spec/storageClassName
      value: nfs-tenant # Must match the name in your StorageClass manifest
    ```
3.  **Update `kustomization.yaml`**: Add both the `storage` directory to your resources and the patch:
    ```yaml
    resources:
      - ../../base
      - ./storage # This includes the nfs-storageclass.yaml

    patches:
      - path: patches/storageclass-patch.yaml
        target:
          kind: PersistentVolumeClaim
    ```

By following this pattern, you can easily adapt any tenant to a different storage backend without ever touching the base application manifests.

# Longhorn

**Official Website:** [https://longhorn.io/](https://longhorn.io/)

## Purpose in Architecture

`Longhorn` is a **distributed, cloud-native block storage solution for Kubernetes**. Its primary function is to provide replicated, highly available persistent volumes (`PersistentVolumes`) to our stateful applications (`StatefulSets` and `Deployments`).

It is one of the key implementations of our [Storage Strategy](./storage-strategy.md) for environments that require resilience and advanced storage management.

## Basic Operation

-   **Distributed Storage:** Longhorn uses the free space on the disks of the Kubernetes cluster nodes to create a distributed storage pool.
-   **Replication:** When a volume is created, Longhorn automatically replicates its data across multiple nodes. If a node fails, the data is still available from another replica on a healthy node.
-   **User Interface:** It provides a very comprehensive dashboard for managing volumes, snapshots, backups, and storage nodes.
-   **Advanced Features:**
    -   **Snapshots:** Allows creating point-in-time snapshots of volumes.
    -   **Backups:** Can back up volumes to S3-compatible external storage (like [Minio](./minio.md)) or NFS.
    -   **Live Resizing:** Allows increasing the size of a volume without needing to unmount it.

## Project Integration

-   **Installation:** Longhorn is installed as an application in the cluster, usually via its Helm chart or manifests. Its base configuration is located in `k8s/base/apps/longhorn/`.
-   **StorageClass:** Once installed, it creates a `StorageClass` named `longhorn`.
-   **Usage by Applications:** Applications that need persistent and resilient storage create a `PersistentVolumeClaim` (PVC) specifying `storageClassName: longhorn`. Longhorn then dynamically provisions a `PersistentVolume` (PV) that satisfies this request.
-   **Backup and Disaster Recovery:** In our architecture, Longhorn is configured to use [Minio](./minio.md) as a backup target, providing a robust solution for disaster recovery.

`Longhorn` is the preferred solution for critical applications that cannot afford data loss, such as databases or important stateful applications.

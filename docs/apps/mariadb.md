# MariaDB

**Official Website:** [https://mariadb.org/](https://mariadb.org/)

## Purpose in Architecture

`MariaDB` is a community-developed, commercially supported fork of the MySQL relational database management system. It is a robust, scalable, and reliable **SQL database** solution.

Its role in our component catalog is to provide a general-purpose, open-source relational database for applications that require one. It is often used as a backend for services, content management systems, or as a data warehouse.

## Basic Operation

-   **Relational Database:** Stores data in tables with predefined schemas, rows, and columns.
-   **SQL Interface:** Interacted with using the standard Structured Query Language (SQL).
-   **High Performance:** Known for its performance, stability, and strong community support.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/databases/mariadb/`.
-   **Inclusion in Tenant:** An `overlay` can deploy MariaDB for applications that need a SQL database.
-   **Stateful Deployment:** It is deployed as a `StatefulSet` to ensure it has a stable network identity and persistent storage.
-   **Persistence:** A `PersistentVolumeClaim` is used to store the database files. This is a critical component, and the volume should be backed by a resilient storage solution like [Longhorn](./longhorn.md) and be regularly backed up.
-   **Configuration and Secrets:**
    -   A `ConfigMap` can be used to provide custom `my.cnf` configurations.
    -   A `Secret` is used to manage sensitive information, most importantly the `MYSQL_ROOT_PASSWORD` and credentials for application-specific users. These secrets must be defined in the `overlay`.
-   **Exposure:** MariaDB is almost never exposed publicly. Applications running within the Kubernetes cluster connect to it using its internal `Service` name (e.g., `mariadb-service.database.svc.cluster.local`).

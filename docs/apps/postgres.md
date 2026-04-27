# PostgreSQL

**Official Website:** [https://www.postgresql.org/](https://www.postgresql.org/)

## Purpose in Architecture

`PostgreSQL`, often simply `Postgres`, is a powerful, open-source object-relational database system with over 30 years of active development that has earned it a strong reputation for reliability, feature robustness, and performance.

It serves as a high-performance, feature-rich **SQL database** solution in our component catalog. It's an excellent choice for complex applications, data warehousing, and when advanced SQL features are required. For example, it is the preferred database for the `n8n` component.

## Basic Operation

-   **Object-Relational Database:** Extends the SQL model by adding object-oriented features, such as inheritance.
-   **Extensibility:** Highly extensible, supporting custom data types, operators, and functions.
-   **Concurrency:** Features a sophisticated Multi-Version Concurrency Control (MVCC) system to handle many concurrent users effectively.
-   **Advanced Features:** Known for its support for JSON/JSONB data types, full-text search, and geospatial data via the PostGIS extension.

## Project Integration

-   **Component:** The configuration is available as a reusable component in `k8s/components/apps/databases/postgres/`.
-   **Inclusion in Tenant:** An `overlay` can deploy a PostgreSQL instance. It is deployed automatically as a dependency of the `n8n` component.
-   **Stateful Deployment:** It is deployed as a `StatefulSet` to ensure a stable network identity and persistent storage.
-   **Persistence:** A `PersistentVolumeClaim` is used to store the database files. This volume must be backed by a resilient storage solution like [Longhorn](./longhorn.md) and be regularly backed up.
-   **Configuration and Secrets:**
    -   A `Secret` is used to manage the `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` for the instance. These secrets must be defined in the `overlay` when deploying it.
-   **Exposure:** Like MariaDB, PostgreSQL is not exposed publicly. Applications connect to it via its internal `Service` name (e.g., `postgres-service.database.svc.cluster.local`).

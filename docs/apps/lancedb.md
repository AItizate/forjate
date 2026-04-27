# LanceDB

**Official Website:** [https://lancedb.com/](https://lancedb.com/)

## Purpose in Architecture

`LanceDB` is an embedded vector database that stores data in the Lance columnar format, optimized for AI/ML workloads. This component wraps LanceDB in a lightweight REST API server (`setchevest/lancedb-server`), exposing table management, vector search, full-text search (BM25), and hybrid search via HTTP.

It serves as a **unified retrieval store** — vectors, full-text, metadata, and documents all live in the same database. This can replace or complement [Milvus](./milvus.md) for vector search workloads with lower infrastructure overhead (no etcd or MinIO dependencies).

## Basic Operation

-   **REST API:** The server exposes CRUD operations on tables, plus vector, full-text, and hybrid search endpoints on port 8000.
-   **Streamlit UI:** A web-based admin interface on port 8501 for browsing tables, searching data, viewing API reference, and MCP setup instructions.
-   **Lance Format:** Data is stored on disk in the Lance columnar format, providing O(1) random access, native vector indexes (IVF_PQ, IVF_HNSW), and built-in BM25 full-text search.
-   **Hybrid Search:** A single query can combine vector similarity + BM25 keyword matching + metadata filters, with Reciprocal Rank Fusion for score merging.
-   **Multimodal:** Lance natively stores binary blobs (images, PDFs) alongside vectors and metadata in the same table.
-   **Modular Architecture:** The server is structured as an `app/` Python package with separate modules for API routes (`app/api/`), MCP tools (`app/mcp/`), DB connection (`app/db.py`), and UI (`app/ui/`).
-   **Stateful:** Uses a `PersistentVolumeClaim` to persist data across pod restarts.

## Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /v1/tables` | List all tables |
| `POST /v1/tables` | Create a table with initial data |
| `GET /v1/tables/{name}` | Table info (schema, row count) |
| `DELETE /v1/tables/{name}` | Drop a table |
| `POST /v1/tables/{name}/add` | Add rows to a table |
| `POST /v1/tables/{name}/search` | Vector, FTS, or hybrid search |
| `POST /v1/tables/{name}/index` | Create vector or FTS index |

## Search Types

The `/v1/tables/{name}/search` endpoint supports three query types:

```json
// Vector search
{"vector": [0.1, 0.2, ...], "query_type": "vector", "limit": 10}

// Full-text search (BM25)
{"query": "quarterly revenue report", "query_type": "fts", "limit": 10}

// Hybrid (vector + BM25 combined)
{"query": "quarterly revenue report", "query_type": "hybrid", "limit": 10}
```

All search types support metadata filtering via `where`:
```json
{"query": "report", "query_type": "fts", "where": "source = 'finance'", "limit": 10}
```

## Project Integration

-   **Component:** Located in `k8s/components/apps/databases/lancedb/`. Deployed as a `StatefulSet` with persistent storage.
-   **Image:** `setchevest/lancedb-server:0.3.0` — a FastAPI wrapper over LanceDB embedded with Streamlit UI.
-   **Service Exposure:** REST API and MCP at `lancedb.{namespace}.svc.cluster.local:8000`, Streamlit UI at `lancedb.{namespace}.svc.cluster.local:8501`.
-   **Storage:** 10Gi PVC by default. The Lance format is compact — a million 768-dim vectors with metadata fits in ~5GB.
-   **Pipeline Role:** Receives embedded chunks from an ingestion pipeline and serves as the retrieval backend for RAG queries. Works alongside [Docling](./docling.md) for parsing and [Gotenberg](./gotenberg.md) for format conversion.

## LanceDB vs Milvus

| | LanceDB | Milvus |
|---|---|---|
| **Architecture** | Embedded (wrapped in API) | Client-server (distributed) |
| **K8s footprint** | 1 pod + PVC | 3+ pods (etcd, MinIO, Milvus) |
| **Hybrid search** | Native (vector + BM25 + filters) | Vector + sparse vectors |
| **Multimodal** | Native (blobs + vectors in same table) | Possible but not optimized |
| **ColPali/ColQwen** | Native multi-vector + MaxSim | Not native |
| **Scale** | Single node (~700M vectors proven) | Distributed (billions) |
| **FTS maturity** | Good (Tantivy-based BM25) | Newer, less mature |

Use LanceDB for workloads under ~50 QPS on a single node. Use Milvus when you need distributed scale or GPU-accelerated search.

## MCP Endpoint

The server also exposes an MCP (Model Context Protocol) endpoint at `/mcp` for LLM agents. Tools available:

| Tool | Description |
|---|---|
| `mcp_list_tables` | List all tables |
| `mcp_table_info` | Get schema and row count for a table |
| `mcp_search` | Full-text, hybrid, or vector search with optional filters |

MCP clients (Claude Desktop, OpenClaw, etc.) can connect to `http://lancedb.{namespace}.svc.cluster.local:8000/mcp`.

## Source Code

The server source is maintained at `github.com/AItizate/lancedb-server` (or built from `setchevest/lancedb-server` on Docker Hub).

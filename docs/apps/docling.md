# Docling

**Official Website:** [https://ds4sd.github.io/docling/](https://ds4sd.github.io/docling/)

## Purpose in Architecture

`Docling` is an AI-powered document parsing service developed by IBM. It converts documents (PDF, DOCX, PPTX, HTML, images) into structured Markdown or JSON, preserving document hierarchy, tables, and layout. Its role is to provide **intelligent document parsing as a service** for ingestion pipelines, replacing simpler tools like raw OCR or basic text extraction.

It is the entry point for document ingestion — converting raw files into structured, LLM-optimized content ready for chunking, embedding, and indexing.

## Basic Operation

-   **REST API:** Docling Serve exposes a FastAPI-based API for synchronous and asynchronous document conversion and chunking.
-   **AI Layout Analysis:** Uses a trained layout model (DocLayNet-based) to detect headings, paragraphs, tables, figures, and other elements.
-   **Table Extraction:** TableFormer model extracts table structure and content, including merged cells and complex layouts.
-   **OCR:** Built-in OCR (EasyOCR / RapidOCR) for scanned documents and images.
-   **Chunking:** Built-in hierarchical chunking that respects document structure (sections, subsections, paragraphs).
-   **Stateless:** No persistent storage required. Models are baked into the container image.

## Key Endpoints

| Endpoint | Description |
|---|---|
| `POST /v1/convert/file` | Convert an uploaded file (sync) |
| `POST /v1/convert/source` | Convert from URL (sync) |
| `POST /v1/convert/file/async` | Convert file (async, returns task_id) |
| `POST /v1/chunk/{chunker}/file` | Convert and chunk a file |
| `GET /v1/status/poll/{task_id}` | Poll async task status |
| `GET /v1/result/{task_id}` | Fetch async task result |
| `GET /health` | Health check |
| `GET /readyz` | Readiness probe |
| `GET /livez` | Liveness probe |
| `GET /metrics` | Prometheus metrics |

## Project Integration

-   **Component:** Located in `k8s/components/apps/document-processing/docling/`. Deployed as a `Deployment` (stateless, models baked into image).
-   **Image:** `ghcr.io/docling-project/docling-serve-cpu:latest` (CPU-only, ~4.4GB). GPU variants available (`docling-serve-cu128`).
-   **Service Exposure:** Exposed internally via `docling.{namespace}.svc.cluster.local:5001`.
-   **Pipeline Role:** Receives raw documents from an ingestion pipeline, returns structured Markdown with hierarchy metadata. Output feeds into chunking and embedding stages.
-   **Consumption:** Agents, Temporal workflows, or any service can POST documents to the API. Works alongside [Gotenberg](./gotenberg.md) — use Gotenberg for format conversion (PPT→PDF) and Docling for intelligent parsing.

## Customization via Overlays

Tenants can patch the Deployment environment variables:

| Variable | Default | Description |
|---|---|---|
| `DOCLING_SERVE_ENG_LOC_NUM_WORKERS` | `2` | Number of concurrent conversion workers |
| `DOCLING_SERVE_ENABLE_UI` | `false` | Enable Gradio web UI at `/ui` |
| `DOCLING_SERVE_API_KEY` | `` | Optional API key for authentication |
| `DOCLING_SERVE_MAX_NUM_PAGES` | unlimited | Maximum pages per document |
| `DOCLING_SERVE_MAX_FILE_SIZE` | unlimited | Maximum upload file size |

## Usage Example

```bash
# Convert a PDF to structured markdown
curl -X POST http://docling.ai-tools.svc.cluster.local:5001/v1/convert/file \
  -F "files=@document.pdf"

# Convert from URL
curl -X POST http://docling.ai-tools.svc.cluster.local:5001/v1/convert/source \
  -H "Content-Type: application/json" \
  -d '{"sources": [{"kind": "http", "url": "https://example.com/report.pdf"}]}'
```

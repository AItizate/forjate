#!/usr/bin/env bash
# Register the Forjate wiki with qmd, the on-device hybrid search engine
# (BM25 + vector + LLM rerank) recommended by the LLM Wiki pattern.
#
# The context strings are not decoration: qmd returns them alongside matches so
# an agent can tell a compiled wiki page from human prose from raw YAML before
# deciding what to open. Keep them accurate.
#
# Usage:  ./scripts/wiki-search-setup.sh [--reembed]

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v qmd >/dev/null 2>&1; then
  echo "qmd not found. Install it with: npm install -g @tobilu/qmd" >&2
  exit 1
fi

echo "==> registering collections"
qmd collection add "$REPO/wiki"  --name forjate-wiki  2>/dev/null || echo "    forjate-wiki already registered"
qmd collection add "$REPO/docs"  --name forjate-docs  2>/dev/null || echo "    forjate-docs already registered"
qmd collection add "$REPO/k8s"   --name forjate-k8s   2>/dev/null || echo "    forjate-k8s already registered"

echo "==> setting context"
qmd context add qmd://forjate-wiki \
  "Compiled wiki for the Forjate Kubernetes factory. Machine-generated from the Kustomize tree: one page per component, overlay and base app, each listing declared resources, container images, patches and which overlays consume it. Authoritative for what is actually declared in the tree. Start at index.md." || true

qmd context add qmd://forjate-docs \
  "Human-written documentation for Forjate: architecture rationale, onboarding guides, the lab-to-production path, business framing. Explains why and how to use the factory. Not generated, not guaranteed to match the current YAML." || true

qmd context add qmd://forjate-k8s \
  "The raw Kustomize source tree: base/, components/ and overlays/. The ultimate source of truth. Search here to verify a claim or read the exact manifest; prefer the wiki collection for orientation." || true

if [[ "${1:-}" == "--reembed" ]]; then
  echo "==> indexing and embedding (first run downloads the local model)"
  qmd update
  qmd embed
fi

echo "==> status"
qmd status || true

cat <<'USAGE'

Ready. Examples:

  qmd search "sealed secrets" -c forjate-wiki
  qmd query  "which overlays use postgres" -c forjate-wiki
  qmd query  "how does a tenant pin a factory version" --all --files --min-score 0.4

Re-run `qmd embed` after each `wiki-compile.py` run.
USAGE

#!/usr/bin/env bash
# One command to bring the wiki back in sync after changing k8s/**:
# recompile, health-check, and refresh the local search index.
#
# Usage:  ./scripts/wiki-update.sh [--no-search]

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

echo "==> compiling wiki from k8s/"
poetry run python scripts/wiki-compile.py

echo
echo "==> linting"
# Non-zero means hard failures (drift, schema, dangling). Surface them but do
# not abort the search refresh — a wiki with findings is still worth indexing.
poetry run python scripts/wiki-lint.py || echo "    (lint reported hard failures — see above)"

if [[ "${1:-}" != "--no-search" ]] && command -v qmd >/dev/null 2>&1; then
  echo
  echo "==> refreshing qmd index"
  # `qmd update` re-scans the collections for new/changed/removed files.
  # `qmd embed` only vectorises what the index already knows about, so running
  # embed alone silently leaves brand-new pages unsearchable.
  qmd update
  qmd embed
fi

echo
echo "Done. Recent history:"
grep "^## \[" wiki/log.md | tail -3

#!/usr/bin/env bash
# Repo-wide check, run by .github/workflows/validate-kustomize.yml; the logic and its rules: repo_checks.py pins.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
PY="${here}/../../.venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" "${here}/repo_checks.py" pins "$@"

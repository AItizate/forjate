#!/usr/bin/env bash
# =============================================================================
# destroy.sh — Tear down the quickstart cluster and remove its kubeconfig.
# =============================================================================

set -euo pipefail

CLUSTER_NAME="forjate-quickstart"
KUBECONFIG_OUTPUT="${HOME}/.kube/${CLUSTER_NAME}.yaml"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log()  { echo -e "${GREEN}[✓]${RESET} $*"; }
info() { echo -e "${BLUE}[→]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }

command -v k3d >/dev/null 2>&1 || { echo "k3d not installed; nothing to destroy." >&2; exit 0; }

if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  info "Deleting cluster '${CLUSTER_NAME}'..."
  k3d cluster delete "$CLUSTER_NAME"
  log "Cluster deleted"
else
  warn "Cluster '${CLUSTER_NAME}' not found"
fi

if [[ -f "$KUBECONFIG_OUTPUT" ]]; then
  rm -f "$KUBECONFIG_OUTPUT"
  log "Removed ${KUBECONFIG_OUTPUT}"
fi

echo ""
log "Done."

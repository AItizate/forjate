#!/usr/bin/env bash
# =============================================================================
# 01_init_cluster.sh — Create a local k3d cluster for the forjate quickstart.
#
# Usage: ./01_init_cluster.sh
# Idempotent: re-running on an existing cluster prints status and exits 0.
# =============================================================================

set -euo pipefail

CLUSTER_NAME="forjate-quickstart"
K3D_IMAGE="rancher/k3s:v1.31.3-k3s1"
KUBECONFIG_OUTPUT="${HOME}/.kube/${CLUSTER_NAME}.yaml"

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info()  { echo -e "${BLUE}[→]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

# ── Deps check ───────────────────────────────────────────────────────────────
missing=()
for cmd in k3d kubectl; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if (( ${#missing[@]} > 0 )); then
  echo "Missing required commands: ${missing[*]}" >&2
  echo "" >&2
  echo "Install:" >&2
  echo "  k3d:     https://k3d.io/#installation" >&2
  echo "  kubectl: https://kubernetes.io/docs/tasks/tools/" >&2
  exit 1
fi
log "k3d: $(k3d version | head -1)"
log "kubectl: $(kubectl version --client -o yaml 2>/dev/null | grep gitVersion | head -1 | awk '{print $2}')"

# ── Cluster ──────────────────────────────────────────────────────────────────
if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  warn "Cluster '${CLUSTER_NAME}' already exists. Skipping creation."
else
  info "Creating k3d cluster '${CLUSTER_NAME}' (1 server + 1 agent)..."
  k3d cluster create "$CLUSTER_NAME" \
    --image "$K3D_IMAGE" \
    --agents 1 \
    --port "8080:80@loadbalancer" \
    --port "4443:443@loadbalancer" \
    --k3s-arg "--disable=traefik@server:0" \
    --kubeconfig-update-default=false \
    --wait
  log "Cluster created"
fi

# ── Kubeconfig ───────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$KUBECONFIG_OUTPUT")"
k3d kubeconfig get "$CLUSTER_NAME" > "$KUBECONFIG_OUTPUT"
log "Kubeconfig written to ${KUBECONFIG_OUTPUT}"

export KUBECONFIG="$KUBECONFIG_OUTPUT"
info "Waiting for node to be Ready..."
kubectl wait --for=condition=Ready node --all --timeout=120s >/dev/null
log "Node Ready: $(kubectl get nodes --no-headers | wc -l | tr -d ' ') node(s)"

echo ""
echo -e "${GREEN}Cluster ready.${RESET} Next:"
echo "  export KUBECONFIG=${KUBECONFIG_OUTPUT}"
echo "  ./02_deploy.sh"

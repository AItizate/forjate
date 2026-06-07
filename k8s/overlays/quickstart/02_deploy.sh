#!/usr/bin/env bash
# =============================================================================
# 02_deploy.sh — Apply the quickstart overlay and pull the Gemma 4 model.
#
# Usage: ./02_deploy.sh           # apply + pull model (default)
#        ./02_deploy.sh help      # show usage
# =============================================================================

set -euo pipefail

OVERLAY_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="ai-tools"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e2b-it-q4_K_M}"
PULL_TIMEOUT_SECONDS="${PULL_TIMEOUT_SECONDS:-900}"  # 15 min

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info()  { echo -e "${BLUE}[→]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

show_help() {
  cat <<EOF
Usage: $0 [command]

Commands:
  deploy   (default) Apply the overlay and pull the model.
  help     Show this message.

Env:
  OLLAMA_MODEL              Model tag to pull (default: ${OLLAMA_MODEL})
  PULL_TIMEOUT_SECONDS      Timeout for ollama pull (default: ${PULL_TIMEOUT_SECONDS})
EOF
}

check_deps() {
  local missing=()
  for cmd in kubectl; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if (( ${#missing[@]} > 0 )); then
    error "Missing required commands: ${missing[*]}"
  fi
  kubectl cluster-info >/dev/null 2>&1 \
    || error "kubectl cannot reach a cluster. Run ./01_init_cluster.sh first or set KUBECONFIG."
}

apply_overlay() {
  info "Applying overlay (pass 1 — establish CRDs/namespaces)..."
  kubectl apply -k "$OVERLAY_DIR" 2>&1 | grep -vE "^Warning" || true

  info "Waiting briefly for the API server to register new types..."
  sleep 3

  info "Applying overlay (pass 2 — reconcile remaining)..."
  kubectl apply -k "$OVERLAY_DIR" 2>&1 | grep -vE "^Warning" || true
  log "Overlay applied"
}

wait_for_ollama() {
  info "Waiting for ollama-0 to be Ready (up to 5 min)..."
  kubectl -n "$NAMESPACE" wait --for=condition=Ready pod/ollama-0 --timeout=300s \
    || error "ollama-0 did not become Ready. Try: kubectl -n ${NAMESPACE} describe pod ollama-0"
  log "ollama-0 Ready"
}

pull_model() {
  info "Pulling ${OLLAMA_MODEL} into the cluster (timeout: ${PULL_TIMEOUT_SECONDS}s)..."
  info "First run downloads ~2 GB — be patient on slow links."
  # The container's OLLAMA_HOST is 0.0.0.0 (for `ollama serve`). The CLI inherits
  # it and tries to dial 0.0.0.0 — invalid as a client address. Override to localhost.
  if kubectl -n "$NAMESPACE" exec ollama-0 -- \
       sh -c "OLLAMA_HOST=127.0.0.1:11434 timeout ${PULL_TIMEOUT_SECONDS} ollama pull ${OLLAMA_MODEL}"; then
    log "Model ${OLLAMA_MODEL} pulled"
  else
    error "ollama pull failed or timed out. Check connectivity and retry."
  fi
}

deploy() {
  check_deps
  apply_overlay
  wait_for_ollama
  pull_model
  echo ""
  echo -e "${GREEN}Deployment complete.${RESET} Next:"
  echo "  ./03_validate.sh"
}

case "${1:-deploy}" in
  deploy) deploy ;;
  help|-h|--help) show_help ;;
  *) echo "Unknown command: $1"; show_help; exit 2 ;;
esac

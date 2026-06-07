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

  # Pod Ready == PID 1 running, but `ollama serve` may still be initializing.
  # Poll the in-container API until it accepts requests before issuing the pull.
  info "Waiting for ollama serve to accept connections..."
  for _ in $(seq 1 60); do
    if kubectl -n "$NAMESPACE" exec ollama-0 -- \
         sh -c 'OLLAMA_HOST=127.0.0.1:11434 ollama list' >/dev/null 2>&1; then
      log "ollama serve responding"
      return 0
    fi
    sleep 2
  done
  error "ollama serve did not start responding within 120s. Check: kubectl -n ${NAMESPACE} logs ollama-0"
}

pull_model() {
  info "Pulling ${OLLAMA_MODEL} into the cluster (timeout: ${PULL_TIMEOUT_SECONDS}s)..."
  info "First run downloads ~7 GB — be patient on slow links."
  # The container's OLLAMA_HOST is 0.0.0.0 (for `ollama serve`). The CLI inherits
  # it and tries to dial 0.0.0.0 — invalid as a client address. Override to localhost.
  if kubectl -n "$NAMESPACE" exec ollama-0 -- \
       sh -c "OLLAMA_HOST=127.0.0.1:11434 timeout ${PULL_TIMEOUT_SECONDS} ollama pull ${OLLAMA_MODEL}"; then
    log "Model ${OLLAMA_MODEL} pulled"
  else
    error "ollama pull failed or timed out. Check connectivity and retry."
  fi
}

warmup_model() {
  # Load the model into RAM now so the first user request doesn't pay
  # (load-from-disk + generate). On CPU-only nodes loading a 7 GB model can
  # take 1-3 minutes; doing it here keeps the validation Job fast and predictable.
  # We use `ollama run` (the CLI is the only HTTP client in the image — no curl/wget).
  info "Warming up ${OLLAMA_MODEL} (loading into RAM, up to 5 min)..."
  if kubectl -n "$NAMESPACE" exec ollama-0 -- \
       sh -c "OLLAMA_HOST=127.0.0.1:11434 timeout 300 ollama run ${OLLAMA_MODEL} 'hi' >/dev/null 2>&1"; then
    log "Model warm — ready to answer prompts"
  else
    warn "Warm-up did not complete in 5 min. The validation Job may still time out — re-run 03_validate.sh after a couple of minutes."
  fi
}

apply_validation_job() {
  info "Applying validation Job (model: ${OLLAMA_MODEL})..."
  # Recreate the Job so re-runs don't trip over an existing one in "Complete" status.
  kubectl -n "$NAMESPACE" delete job quickstart-validate --ignore-not-found >/dev/null 2>&1 || true
  # The YAML hardcodes gemma4:e2b-it-q4_K_M as the default (so `kubectl apply -k`
  # works standalone). When the user overrides OLLAMA_MODEL, patch the Job env
  # on the fly so validation tests the same model that was just pulled.
  sed "s|gemma4:e2b-it-q4_K_M|${OLLAMA_MODEL}|g" "${OVERLAY_DIR}/quickstart-validate-job.yaml" \
    | kubectl -n "$NAMESPACE" apply -f - >/dev/null
  log "Validation Job submitted"
}

deploy() {
  check_deps
  apply_overlay
  wait_for_ollama
  pull_model
  warmup_model
  apply_validation_job
  echo ""
  echo -e "${GREEN}Deployment complete.${RESET} Next:"
  echo "  ./03_validate.sh   # waits for the Job and shows its output"
}

case "${1:-deploy}" in
  deploy) deploy ;;
  help|-h|--help) show_help ;;
  *) echo "Unknown command: $1"; show_help; exit 2 ;;
esac

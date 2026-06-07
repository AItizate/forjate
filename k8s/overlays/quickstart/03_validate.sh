#!/usr/bin/env bash
# =============================================================================
# 03_validate.sh — Wait for the in-cluster validation Job and show its logs.
#
# The real validator is `quickstart-validate-job.yaml` (per the overlay
# convention). This script is a convenience wrapper: it waits for that Job
# to finish, prints its output, and exits non-zero if the Job failed.
# =============================================================================

set -euo pipefail

NAMESPACE="ai-tools"
JOB_NAME="quickstart-validate"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-900s}"   # 15 min: covers cold-load + generate on CPU
LOCAL_PORT="${LOCAL_PORT:-4000}"
CHAT_TIMEOUT="${CHAT_TIMEOUT:-120}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; DIM='\033[2m'; RESET='\033[0m'
log()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info()  { echo -e "${BLUE}[→]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

PF_PID=""
cleanup() {
  if [ -n "$PF_PID" ] && kill -0 "$PF_PID" 2>/dev/null; then
    kill "$PF_PID" 2>/dev/null || true
    wait "$PF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

command -v kubectl >/dev/null 2>&1 || error "kubectl not found"
kubectl cluster-info >/dev/null 2>&1 \
  || error "kubectl cannot reach a cluster. Set KUBECONFIG and retry."

if ! kubectl -n "$NAMESPACE" get job "$JOB_NAME" >/dev/null 2>&1; then
  error "Job '${JOB_NAME}' not found in namespace '${NAMESPACE}'. Run ./02_deploy.sh first."
fi

info "Waiting for Job/${JOB_NAME} to finish (timeout: ${WAIT_TIMEOUT})..."
info "First run includes model load + generate on CPU — can take 3-10 min."

# Filter conditions by .type (kubectl 1.36+ adds SuccessCriteriaMet alongside Complete).
set +e
kubectl -n "$NAMESPACE" wait --for=condition=complete "job/${JOB_NAME}" \
  --timeout="$WAIT_TIMEOUT" >/dev/null 2>&1
COMPLETE_RC=$?
set -e

if [ $COMPLETE_RC -eq 0 ]; then
  STATUS="Complete"
elif kubectl -n "$NAMESPACE" get "job/${JOB_NAME}" \
       -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null \
       | grep -q "True"; then
  STATUS="Failed"
else
  STATUS="Timeout"
fi

echo ""
echo "─── Job logs ───────────────────────────────────────────────"
kubectl -n "$NAMESPACE" logs "job/${JOB_NAME}" --tail=200 2>/dev/null || true
echo "────────────────────────────────────────────────────────────"
echo ""

case "$STATUS" in
  Complete)
    MODEL=$(kubectl -n "$NAMESPACE" get "job/${JOB_NAME}" \
              -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LITELLM_MODEL")].value}' 2>/dev/null \
              || echo "gemma3")
    MASTER_KEY=$(kubectl -n "$NAMESPACE" get "job/${JOB_NAME}" \
              -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="LITELLM_MASTER_KEY")].value}' 2>/dev/null \
              || echo "sk-quickstart-localdev-only")
    echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
    echo -e "${GREEN}  Quickstart cluster validated ✅${RESET}"
    echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
    echo ""

    # Skip the interactive REPL if stdin isn't a TTY (CI, redirected, etc.) and just print instructions.
    if [ ! -t 0 ] || [ -n "${NO_CHAT:-}" ]; then
      echo "Talk to the model through LiteLLM (OpenAI-compatible API):"
      echo "  kubectl -n ${NAMESPACE} port-forward svc/litellm ${LOCAL_PORT}:4000"
      echo "  curl http://localhost:${LOCAL_PORT}/v1/chat/completions \\"
      echo "    -H 'Authorization: Bearer ${MASTER_KEY}' \\"
      echo "    -H 'Content-Type: application/json' \\"
      echo "    -d '{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
      exit 0
    fi

    info "Opening port-forward svc/litellm ${LOCAL_PORT}:4000..."
    kubectl -n "$NAMESPACE" port-forward "svc/litellm" "${LOCAL_PORT}:4000" >/dev/null 2>&1 &
    PF_PID=$!
    for _ in $(seq 1 20); do
      if curl -sf --max-time 2 "http://localhost:${LOCAL_PORT}/health/liveliness" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if ! curl -sf --max-time 2 "http://localhost:${LOCAL_PORT}/health/liveliness" >/dev/null 2>&1; then
      error "Port-forward never came up on http://localhost:${LOCAL_PORT}"
    fi
    log "Port-forward ready on http://localhost:${LOCAL_PORT}"

    echo ""
    echo -e "${DIM}Chat with ${MODEL} via LiteLLM. Empty line or Ctrl-C to quit.${RESET}"
    echo -e "${DIM}(The port-forward closes automatically when you exit.)${RESET}"
    echo ""

    while IFS= read -r -p "> " prompt && [ -n "$prompt" ]; do
      payload=$(MODEL="$MODEL" PROMPT="$prompt" python3 -c '
import json, os
print(json.dumps({
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": os.environ["PROMPT"]}],
}))')
      reply=$(curl -sf --max-time "$CHAT_TIMEOUT" \
                -H "Authorization: Bearer ${MASTER_KEY}" \
                -H "Content-Type: application/json" \
                -d "$payload" \
                "http://localhost:${LOCAL_PORT}/v1/chat/completions" \
              | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin)["choices"][0]["message"]["content"])
except Exception as e:
    sys.exit(f"parse error: {e}")
' 2>&1) || { warn "request failed: $reply"; continue; }
      echo -e "${GREEN}${reply}${RESET}"
      echo ""
    done
    echo ""
    log "Bye."
    ;;
  Failed)
    error "Validation Job FAILED. See logs above."
    ;;
  Timeout)
    error "Validation Job did not finish within ${WAIT_TIMEOUT}. See logs above or:
  kubectl -n ${NAMESPACE} describe job/${JOB_NAME}"
    ;;
esac

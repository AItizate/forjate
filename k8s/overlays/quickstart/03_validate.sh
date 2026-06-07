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

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info()  { echo -e "${BLUE}[→]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

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
              || echo "gemma")
    MASTER_KEY=$(kubectl -n "$NAMESPACE" get secret litellm-secret \
                   -o jsonpath='{.data.LITELLM_MASTER_KEY}' 2>/dev/null | base64 -d 2>/dev/null \
                   || echo "sk-quickstart-localdev-only")
    echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
    echo -e "${GREEN}  Quickstart cluster validated ✅${RESET}"
    echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
    echo ""
    echo "Talk to the model through LiteLLM (OpenAI-compatible API):"
    echo "  kubectl -n ${NAMESPACE} port-forward svc/litellm 4000:4000"
    echo "  curl http://localhost:4000/v1/chat/completions \\"
    echo "    -H 'Authorization: Bearer ${MASTER_KEY}' \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
    ;;
  Failed)
    error "Validation Job FAILED. See logs above."
    ;;
  Timeout)
    error "Validation Job did not finish within ${WAIT_TIMEOUT}. See logs above or:
  kubectl -n ${NAMESPACE} describe job/${JOB_NAME}"
    ;;
esac

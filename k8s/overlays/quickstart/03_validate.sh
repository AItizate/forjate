#!/usr/bin/env bash
# =============================================================================
# 03_validate.sh — End-to-end smoke test of the quickstart cluster.
#
# Checks: node Ready, ollama-0 Running, port-forward, prompt round-trip.
# =============================================================================

set -euo pipefail

NAMESPACE="ai-tools"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e2b-it-q4_K_M}"
LOCAL_PORT="${LOCAL_PORT:-11434}"
PROMPT="${PROMPT:-Reply with exactly: hello from forjate}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-300}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info()  { echo -e "${BLUE}[→]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

PF_PID=""
cleanup() {
  if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" 2>/dev/null; then
    kill "$PF_PID" 2>/dev/null || true
    wait "$PF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ── Deps ─────────────────────────────────────────────────────────────────────
for cmd in kubectl curl python3; do
  command -v "$cmd" >/dev/null 2>&1 || error "Missing required command: $cmd"
done

# ── 1. Cluster reachable ────────────────────────────────────────────────────
info "Checking cluster reachable..."
kubectl cluster-info >/dev/null 2>&1 \
  || error "kubectl cannot reach a cluster. Set KUBECONFIG and retry."
log "Cluster reachable"

# ── 2. Nodes Ready ──────────────────────────────────────────────────────────
info "Checking nodes..."
NOT_READY=$(kubectl get nodes --no-headers | awk '$2 != "Ready" {print $1}')
[[ -n "$NOT_READY" ]] && error "Node(s) not Ready: $NOT_READY"
log "All nodes Ready ($(kubectl get nodes --no-headers | wc -l | tr -d ' '))"

# ── 3. ollama-0 Running ─────────────────────────────────────────────────────
info "Checking ollama-0 Running in ${NAMESPACE}..."
POD_PHASE=$(kubectl -n "$NAMESPACE" get pod ollama-0 -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
[[ "$POD_PHASE" == "Running" ]] \
  || error "ollama-0 is in phase '${POD_PHASE:-missing}'. Run: kubectl -n ${NAMESPACE} describe pod ollama-0"
log "ollama-0 Running"

# ── 4. Port-forward ─────────────────────────────────────────────────────────
info "Port-forwarding ollama-service ${LOCAL_PORT}:11434 in background..."
kubectl -n "$NAMESPACE" port-forward svc/ollama-service "${LOCAL_PORT}:11434" >/dev/null 2>&1 &
PF_PID=$!

# Wait until the port responds (max 20s).
for _ in $(seq 1 20); do
  if curl -sf "http://localhost:${LOCAL_PORT}/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf "http://localhost:${LOCAL_PORT}/api/tags" >/dev/null 2>&1 \
  || error "Port-forward never responded on http://localhost:${LOCAL_PORT}"
log "Ollama API responding on http://localhost:${LOCAL_PORT}"

# ── 5. Model present ────────────────────────────────────────────────────────
info "Checking model ${OLLAMA_MODEL} is loaded..."
TAGS_JSON=$(curl -sf "http://localhost:${LOCAL_PORT}/api/tags")
echo "$TAGS_JSON" | python3 -c "
import sys, json
tags = json.load(sys.stdin).get('models', [])
names = [m.get('name','') for m in tags]
target = '${OLLAMA_MODEL}'
if not any(target in n or n.startswith(target.split(':')[0]) for n in names):
    print(f'Model {target} not in {names}', file=sys.stderr)
    sys.exit(1)
" || error "Model ${OLLAMA_MODEL} not loaded. Re-run ./02_deploy.sh."
log "Model ${OLLAMA_MODEL} loaded"

# ── 6. Prompt round-trip ────────────────────────────────────────────────────
info "Sending a test prompt (timeout: ${REQUEST_TIMEOUT_SECONDS}s)..."
PAYLOAD=$(python3 -c "
import json
print(json.dumps({'model': '${OLLAMA_MODEL}', 'prompt': '''${PROMPT}''', 'stream': False}))
")

RESPONSE=$(curl -sf --max-time "$REQUEST_TIMEOUT_SECONDS" \
  -X POST "http://localhost:${LOCAL_PORT}/api/generate" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD") \
  || error "Generation request failed. The model may still be warming up — retry in 30s."

REPLY=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
r = data.get('response', '').strip()
if not r:
    sys.exit(1)
print(r)
") || error "Empty response from model: $RESPONSE"

log "Model replied: $(echo "$REPLY" | head -c 200)"

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
echo -e "${GREEN}  Quickstart cluster validated ✅${RESET}"
echo -e "${GREEN}═════════════════════════════════════════════${RESET}"
echo ""
echo "Talk to the model from your machine while this terminal is open:"
echo "  curl http://localhost:${LOCAL_PORT}/api/generate \\"
echo "    -d '{\"model\":\"${OLLAMA_MODEL}\",\"prompt\":\"Hello\",\"stream\":false}'"
echo ""
echo "(Re-running this script will set up the port-forward again.)"

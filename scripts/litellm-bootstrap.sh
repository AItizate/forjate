#!/usr/bin/env bash
set -euo pipefail

# litellm-bootstrap.sh — Post-deploy script to create LiteLLM teams and virtual keys
#
# Creates a team and service-account keys for apps that consume LiteLLM.
# Idempotent: skips creation if team/key already exists.
#
# Usage:
#   ./litellm-bootstrap.sh --context <k8s-context> --team <team-name> --keys "app1,app2,..."
#
# Example:
#   ./litellm-bootstrap.sh --context my-org --team my-org --keys "affine,n8n"
#
# Output: prints the generated virtual keys (save them — they can't be retrieved later)

CONTEXT=""
TEAM_NAME=""
KEYS_CSV=""
NAMESPACE="ai-tools"
DEPLOY="litellm"
LOCAL_PORT=4000

usage() {
  echo "Usage: $0 --context <k8s-context> --team <team-name> --keys <comma-separated-key-aliases>"
  echo ""
  echo "Options:"
  echo "  --context    Kubernetes context name"
  echo "  --team       Team alias (e.g., my-org, im-u)"
  echo "  --keys       Comma-separated list of key aliases (e.g., affine,n8n)"
  echo "  --namespace  Namespace where LiteLLM runs (default: ai-tools)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --context) CONTEXT="$2"; shift 2 ;;
    --team) TEAM_NAME="$2"; shift 2 ;;
    --keys) KEYS_CSV="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -z "$CONTEXT" || -z "$TEAM_NAME" || -z "$KEYS_CSV" ]] && usage

# Get master key from cluster
MASTER_KEY=$(kubectl --context="$CONTEXT" get secret litellm-secret -n "$NAMESPACE" \
  -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)

if [[ -z "$MASTER_KEY" ]]; then
  echo "ERROR: Could not retrieve LITELLM_MASTER_KEY from context=$CONTEXT namespace=$NAMESPACE"
  exit 1
fi

# Port-forward in background
kubectl --context="$CONTEXT" port-forward "deploy/$DEPLOY" "$LOCAL_PORT:4000" -n "$NAMESPACE" &
PF_PID=$!
trap "kill $PF_PID 2>/dev/null" EXIT
sleep 2

BASE_URL="http://localhost:$LOCAL_PORT"
AUTH="Authorization: Bearer $MASTER_KEY"

# --- Create team (idempotent) ---
EXISTING_TEAMS=$(curl -s "$BASE_URL/team/list" -H "$AUTH")
TEAM_ID=$(echo "$EXISTING_TEAMS" | python3 -c "
import json, sys
teams = json.load(sys.stdin)
for t in teams:
    if t.get('team_alias') == '$TEAM_NAME':
        print(t['team_id'])
        break
" 2>/dev/null || true)

if [[ -n "$TEAM_ID" ]]; then
  echo "Team '$TEAM_NAME' already exists (id: $TEAM_ID)"
else
  echo "Creating team '$TEAM_NAME'..."
  TEAM_RESPONSE=$(curl -s "$BASE_URL/team/new" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "{
      \"team_alias\": \"$TEAM_NAME\",
      \"models\": [\"all-proxy-models\"]
    }")
  TEAM_ID=$(echo "$TEAM_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['team_id'])")
  echo "Created team '$TEAM_NAME' (id: $TEAM_ID)"
fi

# --- Create keys (idempotent) ---
EXISTING_KEYS=$(curl -s "$BASE_URL/team/info?team_id=$TEAM_ID" -H "$AUTH")
EXISTING_KEY_ALIASES=$(echo "$EXISTING_KEYS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
keys = data.get('keys', data.get('team_info', {}).get('keys', []))
for k in keys:
    alias = k.get('key_alias', '')
    if alias:
        print(alias)
" 2>/dev/null || true)

IFS=',' read -ra KEY_ALIASES <<< "$KEYS_CSV"
for ALIAS in "${KEY_ALIASES[@]}"; do
  ALIAS=$(echo "$ALIAS" | xargs)  # trim whitespace
  if echo "$EXISTING_KEY_ALIASES" | grep -qx "$ALIAS"; then
    echo "Key '$ALIAS' already exists in team '$TEAM_NAME' — skipping"
  else
    echo "Creating key '$ALIAS' in team '$TEAM_NAME'..."
    KEY_RESPONSE=$(curl -s "$BASE_URL/key/generate" \
      -H "$AUTH" \
      -H "Content-Type: application/json" \
      -d "{
        \"team_id\": \"$TEAM_ID\",
        \"key_alias\": \"$ALIAS\",
        \"models\": [\"all-proxy-models\"],
        \"metadata\": {\"service_account_id\": \"$ALIAS\"}
      }")
    GENERATED_KEY=$(echo "$KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key'])")
    echo ""
    echo "  >>> KEY for '$ALIAS': $GENERATED_KEY"
    echo "  >>> Save this key — it cannot be retrieved later!"
    echo ""
  fi
done

echo "Done."

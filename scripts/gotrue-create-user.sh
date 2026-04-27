#!/usr/bin/env bash
set -euo pipefail

# gotrue-create-user.sh — Create a user in GoTrue via the admin API
#
# Idempotent: returns success if user already exists.
#
# Usage:
#   ./gotrue-create-user.sh --context <k8s-context> --email <email> [--apps <apps>]
#
# Examples:
#   ./gotrue-create-user.sh --context im-u --email user@example.com
#   ./gotrue-create-user.sh --context im-u --email user@example.com --apps "kb,n8n"
#
# Options:
#   --context    Kubernetes context name (required)
#   --email      User email address (required)
#   --apps       Comma-separated app access list (default: * = all apps)
#   --namespace  Namespace where gotrue-auth runs (default: security)
#   --deploy     GoTrue deployment name (default: gotrue-auth)

CONTEXT=""
EMAIL=""
APPS="*"
NAMESPACE="security"
DEPLOY="gotrue-auth"

usage() {
  echo "Usage: $0 --context <k8s-context> --email <email> [--apps <apps>]"
  echo ""
  echo "Options:"
  echo "  --context    Kubernetes context name"
  echo "  --email      User email address"
  echo "  --apps       Comma-separated app access list (default: * = all)"
  echo "  --namespace  Namespace where gotrue-auth runs (default: security)"
  echo "  --deploy     GoTrue deployment name (default: gotrue-auth)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --context) CONTEXT="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --apps) APPS="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --deploy) DEPLOY="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -z "$CONTEXT" || -z "$EMAIL" ]] && usage

# Build apps JSON array
if [ "$APPS" = "*" ]; then
  APPS_JSON='["*"]'
else
  APPS_JSON=$(echo "$APPS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed 's/.*/"&"/' | paste -sd ',' - | sed 's/^/[/;s/$/]/')
fi

# Generate admin JWT from cluster secret
echo "Retrieving GoTrue JWT secret from context=$CONTEXT namespace=$NAMESPACE..."
JWT_SECRET=$(kubectl --context="$CONTEXT" get secret -n "$NAMESPACE" gotrue-secret \
  -o jsonpath='{.data.GOTRUE_JWT_SECRET}' | base64 -d)

if [[ -z "$JWT_SECRET" ]]; then
  echo "ERROR: Could not retrieve GOTRUE_JWT_SECRET from context=$CONTEXT namespace=$NAMESPACE"
  exit 1
fi

TOKEN=$(python3 -c "
import hmac, hashlib, base64, json, time
secret = '$JWT_SECRET'
h = base64.urlsafe_b64encode(json.dumps({'alg':'HS256','typ':'JWT'}, separators=(',',':')).encode()).rstrip(b'=').decode()
p = base64.urlsafe_b64encode(json.dumps({'role':'supabase_admin','iss':'gotrue','iat':int(time.time()),'exp':int(time.time())+3600}, separators=(',',':')).encode()).rstrip(b'=').decode()
s = base64.urlsafe_b64encode(hmac.new(secret.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
print(f'{h}.{p}.{s}')
")

# Random password (user logs in via OAuth, not password)
PASSWORD=$(openssl rand -base64 32)

# Port-forward in background
LOCAL_PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")
kubectl --context="$CONTEXT" port-forward -n "$NAMESPACE" "deployment/$DEPLOY" "${LOCAL_PORT}:9999" >/dev/null 2>&1 &
PF_PID=$!
trap "kill $PF_PID 2>/dev/null" EXIT
sleep 2

echo "Creating user: $EMAIL (apps: $APPS_JSON)"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "http://localhost:${LOCAL_PORT}/admin/users" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"email_confirm\": true,
    \"app_metadata\": {
      \"provider\": \"google\",
      \"providers\": [\"google\", \"github\"],
      \"apps\": $APPS_JSON
    }
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

case "$HTTP_CODE" in
  200)
    USER_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])")
    echo "OK: $EMAIL created (id: $USER_ID)"
    ;;
  422)
    if echo "$BODY" | grep -q "email_exists"; then
      echo "User $EMAIL already exists — skipping"
    else
      echo "Error 422: $BODY"
      exit 1
    fi
    ;;
  *)
    echo "Error $HTTP_CODE: $BODY"
    exit 1
    ;;
esac

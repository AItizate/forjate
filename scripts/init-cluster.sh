#!/usr/bin/env bash
# =============================================================================
# init-cluster.sh — Idempotent K3s cluster initialization for forjate
# Usage: ./scripts/init-cluster.sh <path-to-env-file>
# Example: ./scripts/init-cluster.sh scripts/init-cluster.im-u.com.env
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log()     { echo -e "${GREEN}[✓]${RESET} $*"; }
info()    { echo -e "${BLUE}[→]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
error()   { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}══ $* ══${RESET}"; }
pause()   { echo -e "\n${YELLOW}[ACTION REQUIRED]${RESET} $*\nPress ENTER when ready..."; read -r; }

# ── Load env ──────────────────────────────────────────────────────────────────
[[ -z "${1:-}" ]] && error "Usage: $0 <env-file>\n  Example: $0 scripts/init-cluster.im-u.com.env"
[[ ! -f "$1" ]]   && error "File not found: $1"
# shellcheck disable=SC1090
source "$1"
log "Config loaded: $1"

# Validate required vars
for var in TENANT_NAME TENANT_DOMAIN OVERLAY_PATH SERVER_HOST SERVER_USER \
           SSH_KEY_PATH KUBECONFIG_PATH GIT_REPO_SSH CF_DNS_TOKEN \
           CF_TUNNEL_TOKEN CF_TUNNEL_ID CF_ACCOUNT_ID \
           GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
  [[ -z "${!var:-}" ]] && error "Required variable not set: $var"
done

export KUBECONFIG="$KUBECONFIG_PATH"

# ── Helper: command_exists ─────────────────────────────────────────────────────
command_exists() { command -v "$1" &>/dev/null; }

# ── Helper: k8s_resource_exists ───────────────────────────────────────────────
k8s_resource_exists() {
  kubectl get "$1" "$2" ${3:+-n "$3"} &>/dev/null 2>&1
}

# ── Helper: cf_api ────────────────────────────────────────────────────────────
cf_api() {
  local method="$1" endpoint="$2" token="$3"; shift 3
  curl -sf -X "$method" "https://api.cloudflare.com/client/v4/${endpoint}" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    "$@"
}

# =============================================================================
# STEP 0 — Local tools
# =============================================================================
step "0. Local prerequisites"

if ! command_exists k3sup; then
  info "Installing k3sup..."
  curl -sLS https://get.k3sup.dev | sudo sh
fi
log "k3sup: $(k3sup version | head -1)"

if ! command_exists helm; then
  info "Installing helm..."
  curl -s https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi
log "helm: $(helm version --short)"

if ! command_exists kubeseal; then
  info "Installing kubeseal..."
  KUBESEAL_VERSION=$(curl -s https://api.github.com/repos/bitnami-labs/sealed-secrets/releases/latest \
    | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
  curl -sL "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz" \
    | sudo tar -xz -C /usr/local/bin kubeseal
fi
log "kubeseal: $(kubeseal --version)"

# =============================================================================
# STEP 1 — Server prerequisites
# =============================================================================
step "1. Server prerequisites (${SERVER_HOST})"

info "Checking SSH connectivity..."
ssh -o ConnectTimeout=5 -i "$SSH_KEY_PATH" "${SERVER_USER}@${SERVER_HOST}" "echo ok" \
  || error "Cannot connect to ${SERVER_USER}@${SERVER_HOST}"

info "Installing curl, open-iscsi, nfs-common on server..."
ssh -i "$SSH_KEY_PATH" "${SERVER_USER}@${SERVER_HOST}" \
  "sudo apt-get update -qq && sudo apt-get install -y curl open-iscsi nfs-common 2>&1 | tail -3 \
   && sudo systemctl enable --now iscsid \
   && echo ok" | grep -E "ok|E:|error" || true
log "Server prerequisites installed"

# =============================================================================
# STEP 2 — K3s install
# =============================================================================
step "2. K3s via k3sup"

mkdir -p "$(dirname "$KUBECONFIG_PATH")"

if kubectl get nodes &>/dev/null 2>&1; then
  log "K3s already installed ($(kubectl get nodes --no-headers | awk '{print $2}'))"
else
  info "Installing K3s on ${SERVER_HOST}..."
  k3sup install \
    --host "$SERVER_HOST" \
    --user "$SERVER_USER" \
    --ssh-key "$SSH_KEY_PATH" \
    --local-path "$KUBECONFIG_PATH" \
    --k3s-extra-args "--disable traefik --disable servicelb"
  log "K3s installed"
fi

info "Waiting for node to be Ready..."
kubectl wait --for=condition=Ready node --all --timeout=60s
log "Node Ready: $(kubectl get nodes --no-headers)"

# =============================================================================
# STEP 3 — Helm charts
# =============================================================================
step "3. Base Helm charts"

helm repo add jetstack   https://charts.jetstack.io --force-update 2>/dev/null
helm repo add longhorn   https://charts.longhorn.io  2>/dev/null || true
helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests 2>/dev/null || true
helm repo update | grep -E "Successfully|Update"

if ! helm status cert-manager -n cert-manager &>/dev/null; then
  info "Installing cert-manager..."
  helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager --create-namespace \
    --version v1.18.2 --set crds.enabled=true
fi
log "cert-manager: $(helm status cert-manager -n cert-manager -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['status'])")"

if ! helm status longhorn -n longhorn-system &>/dev/null; then
  info "Installing Longhorn..."
  helm upgrade --install longhorn longhorn/longhorn \
    --namespace longhorn-system --create-namespace --version 1.9.2
fi
log "longhorn: $(helm status longhorn -n longhorn-system -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['status'])")"

# OAuth2 Proxy requires a values file from the overlay
OAUTH2_VALUES="${OVERLAY_PATH}/oauth2-values.yaml"
if [[ ! -f "$OAUTH2_VALUES" ]]; then
  warn "${OAUTH2_VALUES} not found — generating from template..."
  COOKIE_SECRET=$(python3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
  cat > "$OAUTH2_VALUES" <<EOF
replicaCount: 1
extraArgs:
  provider: google
  client-id: ${GOOGLE_CLIENT_ID}
  client-secret: ${GOOGLE_CLIENT_SECRET}
  cookie-secret: ${COOKIE_SECRET}
  http-address: 0.0.0.0:4180
  redirect-url: https://auth.${TENANT_DOMAIN}/oauth2/callback
  upstream: "static://200"
  cookie-secure: true
  cookie-samesite: lax
  cookie-path: /
  cookie-domain: .${TENANT_DOMAIN}
  cookie-csrf-per-request: true
  cookie-refresh: 8h
  cookie-expire: 48h
  email-domain: "*"
  whitelist-domain: .${TENANT_DOMAIN}
  reverse-proxy: true
  proxy-prefix: /oauth2
  pass-authorization-header: true
  pass-access-token: true
  pass-user-headers: true
  set-authorization-header: true
  set-xauthrequest: true
  skip-provider-button: true
  ssl-insecure-skip-verify: true
  request-logging: true
  auth-logging: true
  standard-logging: true
service:
  type: ClusterIP
  portNumber: 80
ingress:
  enabled: false
EOF
  log "oauth2-values.yaml generated"
fi

if ! helm status oauth2-proxy -n security &>/dev/null; then
  info "Installing OAuth2 Proxy..."
  helm upgrade --install oauth2-proxy oauth2-proxy/oauth2-proxy \
    --namespace security --create-namespace \
    -f "$OAUTH2_VALUES"
fi
log "oauth2-proxy: $(helm status oauth2-proxy -n security -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['status'])")"

# =============================================================================
# STEP 4 — Kustomize overlay (2 passes)
# =============================================================================
step "4. Kustomize overlay (first pass — CRDs)"

info "Apply pass 1..."
kubectl apply -k "$OVERLAY_PATH" 2>&1 | grep -E "created|configured|error|Error" | grep -v "Warning" || true

info "Applying applicationsets CRD server-side (fix for large CRD annotation)..."
kubectl kustomize "$OVERLAY_PATH" | \
  python3 -c "
import sys, yaml
for doc in yaml.safe_load_all(sys.stdin):
    if doc and doc.get('kind') == 'CustomResourceDefinition' \
       and 'applicationsets' in doc.get('metadata',{}).get('name',''):
        print('---'); print(yaml.dump(doc))
" | kubectl apply --server-side -f - 2>&1 | grep -E "serverside|error" || true

info "Apply pass 2..."
kubectl apply -k "$OVERLAY_PATH" 2>&1 | grep -E "created|configured|error|Error" | grep -v "Warning" || true
log "Overlay applied"

# =============================================================================
# STEP 5 — Sealed Secrets
# =============================================================================
step "5. Sealed Secrets"

info "Waiting for sealed-secrets controller..."
kubectl wait --for=condition=Available deployment/sealed-secrets-controller \
  -n kube-system --timeout=120s

seal_secret() {
  local name="$1" namespace="$2" output_path="$3"
  shift 3
  # $@ = args for kubectl create secret
  mkdir -p "$(dirname "$output_path")"
  kubectl create secret generic "$name" --namespace "$namespace" \
    "$@" --dry-run=client -o yaml | \
  kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=kube-system \
    --format yaml > "$output_path"
  kubectl apply -f "$output_path"
}

# 5a. Cloudflare API token for cert-manager
CF_SECRET_PATH="${OVERLAY_PATH}/namespaces/cert-manager/secrets/sealed-cluster-issuer-api-token-secret.yaml"
if ! k8s_resource_exists secret cluster-issuer-api-token-secret cert-manager; then
  info "Sealing Cloudflare DNS token..."
  echo -n "$CF_DNS_TOKEN" | seal_secret cluster-issuer-api-token-secret cert-manager \
    "$CF_SECRET_PATH" --from-file=api-token=/dev/stdin
  log "Cloudflare DNS token sealed"
else
  log "cluster-issuer-api-token-secret already exists"
fi

# 5b. ArgoCD deploy key
ARGOCD_PRIVKEY="${ARGOCD_SSH_KEY_PATH:-/tmp/argocd-deploy-key-${TENANT_NAME}}"
ARGOCD_PUBKEY="${ARGOCD_PRIVKEY}.pub"
ARGOCD_SECRET_PATH="${OVERLAY_PATH}/namespaces/argocd/secrets/sealed-repo-ssh-secret.yaml"

if ! k8s_resource_exists secret repo-ssh-secret argocd; then
  if [[ ! -f "$ARGOCD_PRIVKEY" ]]; then
    info "Generating ArgoCD deploy key..."
    ssh-keygen -t ed25519 -C "argocd@${TENANT_DOMAIN}" -f "$ARGOCD_PRIVKEY" -N "" -q
  fi
  echo ""
  pause "Add this deploy key (READ-ONLY) on GitHub → ${GIT_REPO_SSH%%:*}:${GIT_REPO_SSH##*:} → Settings → Deploy keys:

$(cat "$ARGOCD_PUBKEY")"

  info "Sealing ArgoCD deploy key..."
  kubectl create secret generic repo-ssh-secret \
    --namespace argocd \
    --from-literal=type=git \
    --from-literal=url="$GIT_REPO_SSH" \
    --from-file=sshPrivateKey="$ARGOCD_PRIVKEY" \
    --dry-run=client -o yaml | \
  kubectl label --local -f - \
    "argocd.argoproj.io/secret-type=repository" \
    --dry-run=client -o yaml | \
  kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=kube-system \
    --format yaml > "$ARGOCD_SECRET_PATH"
  mkdir -p "$(dirname "$ARGOCD_SECRET_PATH")"
  kubectl apply -f "$ARGOCD_SECRET_PATH"

  rm -f "$ARGOCD_PRIVKEY" "$ARGOCD_PUBKEY"
  log "ArgoCD deploy key sealed and temp keys removed"
else
  log "repo-ssh-secret already exists"
fi

# 5c. Cloudflare Tunnel token
CF_TUNNEL_SECRET_PATH="${OVERLAY_PATH}/namespaces/cloudflare-tunnel/secrets/sealed-cloudflare-tunnel-secret.yaml"
if ! k8s_resource_exists secret cloudflare-tunnel-secret cloudflare-tunnel; then
  [[ -z "${CF_TUNNEL_TOKEN_VALUE:-}" ]] && error "CF_TUNNEL_TOKEN_VALUE not set (tunnel auth token, not the API token)"
  info "Sealing Cloudflare Tunnel token..."
  echo -n "$CF_TUNNEL_TOKEN_VALUE" | seal_secret cloudflare-tunnel-secret cloudflare-tunnel \
    "$CF_TUNNEL_SECRET_PATH" --from-file=token=/dev/stdin
  log "Cloudflare Tunnel token sealed"
else
  log "cloudflare-tunnel-secret already exists"
fi

# =============================================================================
# STEP 6 — Cloudflare: tunnel routes + DNS
# =============================================================================
step "6. Cloudflare: tunnel routes and DNS"

info "Configuring tunnel routes via API..."
cf_api PUT "accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${CF_TUNNEL_ID}/configurations" \
  "$CF_TUNNEL_TOKEN" \
  --data "{
    \"config\": {
      \"ingress\": [
        {\"hostname\": \"*.${TENANT_DOMAIN}\", \"service\": \"http://traefik.traefik.svc.cluster.local:80\"},
        {\"hostname\": \"${TENANT_DOMAIN}\",   \"service\": \"http://traefik.traefik.svc.cluster.local:80\"},
        {\"service\": \"http_status:404\"}
      ]
    }
  }" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d['success'] else d['errors'])"
log "Tunnel routes configured"

info "Fetching Zone ID for ${TENANT_DOMAIN}..."
ZONE_ID=$(cf_api GET "zones?name=${TENANT_DOMAIN}" "$CF_DNS_TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])")
log "Zone ID: $ZONE_ID"

upsert_dns_cname() {
  local name="$1" content="$2"
  local existing_id
  existing_id=$(cf_api GET "zones/${ZONE_ID}/dns_records?name=${name}.${TENANT_DOMAIN}" "$CF_DNS_TOKEN" \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id'] if r else '')" 2>/dev/null || true)

  if [[ -z "$existing_id" ]]; then
    cf_api POST "zones/${ZONE_ID}/dns_records" "$CF_DNS_TOKEN" \
      --data "{\"type\":\"CNAME\",\"name\":\"${name}\",\"content\":\"${content}\",\"proxied\":true}" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print('created' if d['success'] else d['errors'])"
  else
    cf_api PATCH "zones/${ZONE_ID}/dns_records/${existing_id}" "$CF_DNS_TOKEN" \
      --data "{\"content\":\"${content}\",\"proxied\":true}" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print('updated' if d['success'] else d['errors'])"
  fi
}

TUNNEL_CNAME="${CF_TUNNEL_ID}.cfargotunnel.com"
info "Wildcard CNAME: *.${TENANT_DOMAIN} → ${TUNNEL_CNAME}"
upsert_dns_cname "*" "$TUNNEL_CNAME"
info "Apex CNAME: ${TENANT_DOMAIN} → ${TUNNEL_CNAME}"
upsert_dns_cname "@" "$TUNNEL_CNAME"
log "DNS configured"

# =============================================================================
# STEP 7 — ArgoCD: point to correct branch
# =============================================================================
step "7. ArgoCD GitOps"

info "Waiting for ArgoCD application controller..."
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=120s 2>/dev/null || true

info "Pointing ArgoCD app to branch ${GIT_BRANCH}..."
kubectl patch application main-app -n argocd \
  --type='json' \
  -p="[{\"op\":\"replace\",\"path\":\"/spec/source/targetRevision\",\"value\":\"${GIT_BRANCH}\"}]" \
  2>/dev/null || true
log "ArgoCD configured"

# =============================================================================
# STEP 8 — Commit overlay and push
# =============================================================================
step "8. Git: commit and push overlay"

cd "$(git rev-parse --show-toplevel)"
git add "$OVERLAY_PATH"
if ! git diff --cached --quiet; then
  git commit -m "feat(overlay): ${TENANT_NAME} cluster init [idempotent]"
  git push origin "$GIT_BRANCH"
  log "Overlay pushed to ${GIT_BRANCH}"
else
  log "No new changes to commit"
fi

# =============================================================================
# STEP 9 — Final verification
# =============================================================================
step "9. Final verification"

echo ""
kubectl get nodes
echo ""
kubectl get pods -A | grep -vE "Running|Completed" | grep -v NAMESPACE || echo "All pods OK"
echo ""
kubectl get applications -n argocd 2>/dev/null || true
echo ""
info "Testing https://argocd.${TENANT_DOMAIN}..."
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://argocd.${TENANT_DOMAIN}" 2>/dev/null || echo "000")
[[ "$HTTP_CODE" == "200" ]] && log "argocd.${TENANT_DOMAIN}: HTTP 200 ✅" \
  || warn "argocd.${TENANT_DOMAIN}: HTTP ${HTTP_CODE} (DNS may still be propagating)"

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  Cluster ${TENANT_NAME} initialized ✅${RESET}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${RESET}"
echo ""
echo -e "${YELLOW}Pending (manual):${RESET}"
echo "  • Revoke NOPASSWD: ssh ${SERVER_USER}@${SERVER_HOST} 'sudo rm /etc/sudoers.d/${SERVER_USER}'"
echo "  • Merge PR to main and update ArgoCD targetRevision"
echo "  • Back up sensitive secrets to Drive"

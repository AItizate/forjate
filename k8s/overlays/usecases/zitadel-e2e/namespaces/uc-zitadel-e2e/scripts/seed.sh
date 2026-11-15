#!/bin/sh
# Seed phase: run the hooks of the zitadel component in the order docs/apps/zitadel.md
# ("Delivery requirement") documents for a delivery without Argo CD:
#
#   postgres -> zitadel-init -> zitadel-setup -> the Deployments -> zitadel-bootstrap
#
# Re-runnable: every hook is a fresh Job, and the Deployments are scaled to 0 by the overlay
# on each `up`, so the order holds on a second run too (the stability pass of the nightly).

set -eu

SCRIPTS="${SCRIPTS:-/scripts}"
HOOK_LOG_TAIL=25
export HOOK_LOG_TAIL

step() { echo ""; echo "== $*"; }
die() { echo "  [ERROR] $*"; exit 1; }

hook() {
  HOOK_TIMEOUT="$3" sh "$SCRIPTS/run-hook.sh" "$1" "$2" || die "$1 did not complete (exit $?)"
}

step "PostgreSQL"
kubectl rollout status statefulset/zitadel-postgres --timeout=300s

step "Login V2 service keypair (generated here, never committed)"
if kubectl get secret zitadel-login-service-key > /dev/null 2>&1; then
  echo "  Secret zitadel-login-service-key exists: kept (a new key would roll both Deployments)"
else
  kubectl create secret tls zitadel-login-service-key --cert=/keys/tls.crt --key=/keys/tls.key > /dev/null
  echo "  Secret zitadel-login-service-key created"
fi

step "Hook 1/3: zitadel-init"
hook zitadel-init zitadel-init-run 600

step "Hook 2/3: zitadel-setup"
hook zitadel-setup zitadel-setup-run 900
kubectl get secret zitadel-admin-sa > /dev/null 2>&1 || die "setup did not write the bootstrap service account key (Secret zitadel-admin-sa)"
echo "  Secret zitadel-admin-sa present"

step "Deployments: zitadel and zitadel-login"
kubectl scale deployment/zitadel deployment/zitadel-login --replicas=1
kubectl rollout status deployment/zitadel --timeout=600s
kubectl rollout status deployment/zitadel-login --timeout=600s

step "Hook 3/3: zitadel-bootstrap (the tenant's bootstrap.yaml)"
hook zitadel-bootstrap zitadel-bootstrap-run 900

kubectl get secret zitadel-oidc-portal > /dev/null 2>&1 || die "the bootstrap did not write the Secret zitadel-oidc-portal"
echo ""
echo "Seed complete: init, setup, Deployments and bootstrap ran in order"

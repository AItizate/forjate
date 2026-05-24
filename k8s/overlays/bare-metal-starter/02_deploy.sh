#!/usr/bin/env bash
# bare-metal-starter — Tier Advanced bootstrap, step 2 of 2.
# Applies the overlay and waits for the validation Job to confirm health.

set -euo pipefail

log() { echo -e "\n\e[1;32m$1\e[0m"; }
err() { echo -e "\n\e[1;31m$1\e[0m" >&2; exit 1; }

OVERLAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$OVERLAY_DIR/../../.." && pwd)"

command -v kubectl >/dev/null 2>&1 || err "kubectl not found."
kubectl cluster-info >/dev/null 2>&1 || err "kubectl can't reach a cluster — check KUBECONFIG."

log "Applying $OVERLAY_DIR ..."
kubectl kustomize "$OVERLAY_DIR" | kubectl apply -f -

log "Waiting for Traefik to be ready..."
kubectl rollout status -n traefik deploy/traefik --timeout=180s || true

log "Running health validation Job..."
kubectl -n default delete job/bare-metal-starter-validate --ignore-not-found
kubectl apply -f "$OVERLAY_DIR/validate-job.yaml"
kubectl -n default wait --for=condition=complete job/bare-metal-starter-validate --timeout=180s \
  || err "Validation Job did not complete. Run: kubectl -n default logs job/bare-metal-starter-validate"

log "Cluster healthy. Logs:"
kubectl -n default logs job/bare-metal-starter-validate

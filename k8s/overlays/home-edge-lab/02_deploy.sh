#!/usr/bin/env bash
# home-edge-lab — Tier Advanced bootstrap, step 2 of 2.

set -euo pipefail

log() { echo -e "\n\e[1;32m$1\e[0m"; }
err() { echo -e "\n\e[1;31m$1\e[0m" >&2; exit 1; }

OVERLAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v kubectl >/dev/null 2>&1 || err "kubectl not found."
kubectl cluster-info >/dev/null 2>&1 || err "kubectl can't reach a cluster — check KUBECONFIG."

log "Applying $OVERLAY_DIR ..."
kubectl kustomize "$OVERLAY_DIR" | kubectl apply -f -

log "Waiting for Home Assistant to be ready (this can take a few minutes on a Pi)..."
kubectl rollout status -n home deploy/home-assistant --timeout=300s || true

log "Running home-edge-lab validation Job..."
kubectl -n home delete job/home-edge-lab-validate --ignore-not-found
kubectl apply -f "$OVERLAY_DIR/validate-job.yaml"
kubectl -n home wait --for=condition=complete job/home-edge-lab-validate --timeout=300s \
  || err "Validation Job did not complete. Run: kubectl -n home logs job/home-edge-lab-validate"

log "Home lab healthy. Logs:"
kubectl -n home logs job/home-edge-lab-validate

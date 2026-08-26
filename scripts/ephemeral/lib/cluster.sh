#!/usr/bin/env bash
# =============================================================================
# cluster.sh — k3d cluster lifecycle for ephemeral use-case environments.
#
# Source this file; do not execute it. Requires log.sh to be sourced first.
#
# Cluster naming:
#   shared     → $UC_SHARED_CLUSTER (default: forjate-uc-shared), reused
#   dedicated  → forjate-uc-<usecase-name>, one per use case
#
# Kubeconfigs are written to ~/.kube/<cluster>.yaml and never merged into the
# default kubeconfig, matching the convention used by the overlay bootstrap
# scripts.
# =============================================================================

K3D_IMAGE="${K3D_IMAGE:-rancher/k3s:v1.31.3-k3s1}"
UC_SHARED_CLUSTER="${UC_SHARED_CLUSTER:-forjate-uc-shared}"
UC_CLUSTER_PREFIX="forjate-uc-"

# cluster_name_for <usecase> <isolation> — resolve the k3d cluster name.
cluster_name_for() {
  local name="$1" isolation="$2"
  case "$isolation" in
    shared)    echo "$UC_SHARED_CLUSTER" ;;
    dedicated) echo "${UC_CLUSTER_PREFIX}${name}" ;;
    *)         error "Unknown isolation '${isolation}' (expected: shared | dedicated)" ;;
  esac
}

# kubeconfig_path <cluster> — where this cluster's kubeconfig lives.
kubeconfig_path() {
  echo "${HOME}/.kube/${1}.yaml"
}

# cluster_exists <cluster>
cluster_exists() {
  k3d cluster list "$1" >/dev/null 2>&1
}

# ensure_cluster <cluster> — create if absent, always export KUBECONFIG.
# Idempotent: an existing cluster is reused and only its kubeconfig refreshed.
ensure_cluster() {
  local cluster="$1"
  local kubeconfig
  kubeconfig="$(kubeconfig_path "$cluster")"

  if cluster_exists "$cluster"; then
    info "Reusing existing cluster '${cluster}'"
  else
    info "Creating k3d cluster '${cluster}' (1 server + 1 agent)..."
    # No host port mappings: use-case environments are consumed in-cluster or
    # through `kubectl port-forward`, so several clusters can coexist without
    # fighting over 8080/4443 with the quickstart overlay.
    k3d cluster create "$cluster" \
      --image "$K3D_IMAGE" \
      --agents 1 \
      --k3s-arg "--disable=traefik@server:0" \
      --kubeconfig-update-default=false \
      --wait
    log "Cluster '${cluster}' created"
  fi

  mkdir -p "$(dirname "$kubeconfig")"
  k3d kubeconfig get "$cluster" > "$kubeconfig"
  export KUBECONFIG="$kubeconfig"

  kubectl wait --for=condition=Ready node --all --timeout=120s >/dev/null
  log "Cluster ready — KUBECONFIG=${kubeconfig}"
}

# use_cluster <cluster> — point KUBECONFIG at an existing cluster, or fail.
use_cluster() {
  local cluster="$1" kubeconfig
  cluster_exists "$cluster" || error "Cluster '${cluster}' does not exist. Run 'up' first."
  kubeconfig="$(kubeconfig_path "$cluster")"
  k3d kubeconfig get "$cluster" > "$kubeconfig"
  export KUBECONFIG="$kubeconfig"
}

# delete_cluster <cluster> — remove the cluster and its kubeconfig.
delete_cluster() {
  local cluster="$1" kubeconfig
  kubeconfig="$(kubeconfig_path "$cluster")"

  if cluster_exists "$cluster"; then
    info "Deleting cluster '${cluster}'..."
    k3d cluster delete "$cluster" >/dev/null
    log "Cluster '${cluster}' deleted"
  else
    warn "Cluster '${cluster}' does not exist — nothing to delete"
  fi
  rm -f "$kubeconfig"
}

# list_uc_clusters — every ephemeral cluster except the shared one.
list_uc_clusters() {
  k3d cluster list --no-headers 2>/dev/null \
    | awk '{print $1}' \
    | grep "^${UC_CLUSTER_PREFIX}" \
    | grep -v "^${UC_SHARED_CLUSTER}$" \
    || true
}

# cluster_created_at <cluster> — RFC3339 creation time of the server node.
# k3d exposes no creation timestamp, so we read it from the backing container.
cluster_created_at() {
  docker inspect -f '{{.Created}}' "k3d-${1}-server-0" 2>/dev/null || echo ""
}

#!/usr/bin/env bash
# bare-metal-starter — Tier Advanced bootstrap, step 1 of 2.
#
# Assumes you already have ssh access to the target node(s). Installs k3s
# in HA mode using k3sup. Edit NODES and SSH_USER for your environment.

set -euo pipefail

# --- Configuration ---
SSH_USER="${SSH_USER:-root}"
NODES=(
  # "192.168.1.10"
  # "192.168.1.11"
  # "192.168.1.12"
)
K3S_VERSION="${K3S_VERSION:-v1.30.5+k3s1}"
CLUSTER_NAME="${CLUSTER_NAME:-bare-metal-starter}"

# --- Sanity checks ---
log() { echo -e "\n\e[1;32m$1\e[0m"; }
err() { echo -e "\n\e[1;31m$1\e[0m" >&2; exit 1; }

[ "${#NODES[@]}" -ge 1 ] || err "Edit NODES at the top of this script to point at your servers."
command -v k3sup >/dev/null 2>&1 || err "k3sup not found. Install: https://github.com/alexellis/k3sup"
command -v kubectl >/dev/null 2>&1 || err "kubectl not found."

# --- Install k3s on the first node as server (embedded etcd) ---
SERVER="${NODES[0]}"
log "Installing k3s server on $SERVER (embedded etcd, single-node HA)..."
k3sup install \
  --ip "$SERVER" \
  --user "$SSH_USER" \
  --cluster \
  --k3s-version "$K3S_VERSION" \
  --k3s-extra-args "--disable=traefik --disable=servicelb" \
  --local-path "$HOME/.kube/$CLUSTER_NAME.yaml" \
  --context "$CLUSTER_NAME"

# --- Join remaining nodes ---
for i in "${!NODES[@]}"; do
  [ "$i" -eq 0 ] && continue
  NODE="${NODES[$i]}"
  log "Joining server $NODE to the cluster..."
  k3sup join \
    --ip "$NODE" \
    --user "$SSH_USER" \
    --server-ip "$SERVER" \
    --server \
    --k3s-version "$K3S_VERSION"
done

log "Cluster bootstrapped. Set:"
echo "  export KUBECONFIG=\"$HOME/.kube/$CLUSTER_NAME.yaml\""
echo "Then run: ./02_deploy.sh"

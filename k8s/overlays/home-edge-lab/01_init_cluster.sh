#!/usr/bin/env bash
# home-edge-lab — Tier Advanced bootstrap, step 1 of 2.
#
# Installs k3s on a single Raspberry Pi (or any single Linux box). Run this
# either ON the Pi (PI_HOST=local) or against it over SSH (PI_HOST=<ip>).
# k3sup handles both.

set -euo pipefail

PI_HOST="${PI_HOST:-local}"   # set to the Pi's IP for remote install
SSH_USER="${SSH_USER:-pi}"
K3S_VERSION="${K3S_VERSION:-v1.30.5+k3s1}"
CLUSTER_NAME="${CLUSTER_NAME:-home-edge-lab}"

log() { echo -e "\n\e[1;32m$1\e[0m"; }
err() { echo -e "\n\e[1;31m$1\e[0m" >&2; exit 1; }

command -v k3sup >/dev/null 2>&1 || err "k3sup not found. Install: https://github.com/alexellis/k3sup"

if [ "$PI_HOST" = "local" ]; then
  log "Installing k3s locally..."
  k3sup install \
    --local \
    --k3s-version "$K3S_VERSION" \
    --k3s-extra-args "--disable=traefik --disable=servicelb" \
    --local-path "$HOME/.kube/$CLUSTER_NAME.yaml" \
    --context "$CLUSTER_NAME"
else
  log "Installing k3s on $PI_HOST over SSH..."
  k3sup install \
    --ip "$PI_HOST" \
    --user "$SSH_USER" \
    --k3s-version "$K3S_VERSION" \
    --k3s-extra-args "--disable=traefik --disable=servicelb" \
    --local-path "$HOME/.kube/$CLUSTER_NAME.yaml" \
    --context "$CLUSTER_NAME"
fi

log "Cluster bootstrapped. Set:"
echo "  export KUBECONFIG=\"$HOME/.kube/$CLUSTER_NAME.yaml\""
echo ""
echo "If your NAS exposes NFS, mount it now and consider adding it as a"
echo "Longhorn-capable extra disk or as an NFS PersistentVolume source."
echo ""
echo "Then run: ./02_deploy.sh"

#!/usr/bin/env bash
# home-edge-lab — uninstall the overlay. Does NOT touch the Pi's k3s install.
set -euo pipefail
OVERLAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Deleting overlay resources from current cluster..."
kubectl kustomize "$OVERLAY_DIR" | kubectl delete --ignore-not-found -f -
echo "To wipe k3s from the Pi: sh /usr/local/bin/k3s-uninstall.sh"

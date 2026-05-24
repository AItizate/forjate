#!/usr/bin/env bash
# bare-metal-starter — uninstall the overlay from the current cluster.
# Does NOT touch the cluster itself (use k3sup uninstall on each node for that).

set -euo pipefail
OVERLAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Deleting overlay resources from current cluster..."
kubectl kustomize "$OVERLAY_DIR" | kubectl delete --ignore-not-found -f -
echo "Done. Nodes were NOT touched. To wipe k3s from a node:"
echo "  ssh root@<NODE> 'sh /usr/local/bin/k3s-uninstall.sh'  # server"
echo "  ssh root@<NODE> 'sh /usr/local/bin/k3s-agent-uninstall.sh'  # agent"

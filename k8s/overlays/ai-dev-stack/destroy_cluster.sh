#!/bin/bash
# Script to uninstall k3s from master and worker nodes

set -e

CLUSTER_NAME="ai-dev-stack"

# Uninstall from master node
echo "Deleting k3d cluster $CLUSTER_NAME..."
k3d cluster delete "$CLUSTER_NAME"
echo "K3s cluster uninstallation complete."

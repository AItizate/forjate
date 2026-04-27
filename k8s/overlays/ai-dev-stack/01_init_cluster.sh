#!/bin/bash
# Script to create a 2-node k3d cluster for the ai-dev-stack environment.

set -e

CLUSTER_NAME="ai-dev-stack"
K3D_IMAGE="rancher/k3s:v1.28.2-k3s1"

echo "Creating k3d cluster '$CLUSTER_NAME' with 2 nodes..."

k3d cluster create "$CLUSTER_NAME" \
  --image "$K3D_IMAGE" \
  --agents 1 \
  --port "8080:80@loadbalancer" \
  --port "4443:443@loadbalancer" \
  --k3s-arg "--disable=traefik@server:0" \
  --kubeconfig-update-default=false

KUBECONFIG_OUTPUT="$HOME/.kube/$CLUSTER_NAME.yaml"
k3d kubeconfig get "$CLUSTER_NAME" > "$KUBECONFIG_OUTPUT"
k3d kubeconfig merge "$CLUSTER_NAME" --kubeconfig-merge-default

echo "Cluster '$CLUSTER_NAME' created successfully."
echo "Kubeconfig saved to '$KUBECONFIG_OUTPUT'."
echo "You can now use the cluster by setting the KUBECONFIG environment variable:"
echo "export KUBECONFIG=$PWD/$KUBECONFIG_OUTPUT"

#!/bin/bash
# Script to add Helm repos and deploy essential Helm charts for the LOCAL DEV environment.

set -e

echo "Adding essential Helm repositories for Dev..."
helm repo add jetstack https://charts.jetstack.io
helm repo update

echo "Installing cert-manager for Dev..."
# We use a specific version and ensure CRDs are installed by the chart
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.13.2 \
  --set installCRDs=true

echo "Waiting for cert-manager webhook to be ready..."
# This wait is crucial to ensure the CRDs are recognized by the API server before applying Kustomize
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=120s

echo "Local Dev Helm chart deployment complete."

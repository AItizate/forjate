#!/bin/bash
# Generate a kubeconfig file for a ServiceAccount with limited RBAC access.
# Usage: ./generate-kubeconfig.sh <service-account-name> [namespace] [token-duration]
#
# Examples:
#   ./generate-kubeconfig.sh sa-readonly-user my-rbac
#   ./generate-kubeconfig.sh sa-developer-user my-rbac 8760h
#   ./generate-kubeconfig.sh sa-agent my-rbac 720h

set -euo pipefail

SA_NAME="${1:?Usage: $0 <service-account-name> <namespace> [token-duration]}"
NAMESPACE="${2:?Usage: $0 <service-account-name> <namespace> [token-duration]}"
DURATION="${3:-8760h}"
OUTPUT_FILE="${SA_NAME}-kubeconfig.yaml"

CLUSTER_NAME=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}')
SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CA_DATA=$(kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

echo "Creating token for ServiceAccount ${SA_NAME} in namespace ${NAMESPACE} (duration: ${DURATION})..."
TOKEN=$(kubectl create token "${SA_NAME}" -n "${NAMESPACE}" --duration="${DURATION}")

cat > "${OUTPUT_FILE}" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: ${CLUSTER_NAME}
    cluster:
      server: ${SERVER}
      certificate-authority-data: ${CA_DATA}
contexts:
  - name: ${CLUSTER_NAME}-${SA_NAME}
    context:
      cluster: ${CLUSTER_NAME}
      user: ${SA_NAME}
users:
  - name: ${SA_NAME}
    user:
      token: ${TOKEN}
current-context: ${CLUSTER_NAME}-${SA_NAME}
EOF

echo "Kubeconfig written to ${OUTPUT_FILE}"
echo ""
echo "To use it:"
echo "  export KUBECONFIG=$(pwd)/${OUTPUT_FILE}"
echo "  kubectl get pods -A"

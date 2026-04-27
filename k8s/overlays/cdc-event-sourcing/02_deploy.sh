#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FACTORY_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Install cert-manager (required before kustomize apply — CRDs must exist)
echo "Installing cert-manager..."
helm repo add jetstack https://charts.jetstack.io --force-update
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.13.2 \
  --set installCRDs=true
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=120s

# Apply the overlay
echo "Applying cdc-event-sourcing overlay..."
kubectl apply -k "$FACTORY_ROOT/k8s/overlays/cdc-event-sourcing"

echo ""
echo "Deployment complete. Event sourcing stack:"
echo "  MongoDB RS  → mongodb.event-sourcing.svc.cluster.local:27017"
echo "  RabbitMQ    → rabbitmq.event-sourcing.svc.cluster.local:5672"
echo "              → Management UI: kubectl port-forward svc/rabbitmq 15672:15672 -n event-sourcing"
echo "  Debezium    → watching testdb.events, routing key: cdc.testdb.events"
echo ""
echo "To trigger a test event:"
echo "  kubectl exec -it statefulset/mongodb -n event-sourcing -- mongosh -u admin -p changeme --authenticationDatabase admin"
echo "  > use testdb"
echo "  > db.events.insertOne({ type: 'user.created', payload: { id: 1, name: 'Alice' } })"

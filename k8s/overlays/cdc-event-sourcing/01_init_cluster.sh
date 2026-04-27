#!/bin/bash
set -e

echo "Creating k3d cluster cdc-event-sourcing..."
k3d cluster create cdc-event-sourcing \
  --agents 1 \
  -p "8080:80@loadbalancer" \
  -p "4443:443@loadbalancer" \
  --k3s-arg "--disable=traefik@server:0"

echo "Cluster cdc-event-sourcing created successfully."
echo "Run ./02_deploy.sh to deploy the overlay."

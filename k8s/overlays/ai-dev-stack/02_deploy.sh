#!/bin/bash

# setup.sh: Script to manage the bare-metal environment deployment.

set -e # Exit immediately if a command fails.

# --- Configuration ---
KUSTOMIZE_OVERLAY_DIR="."
HELM_SCRIPT="$KUSTOMIZE_OVERLAY_DIR/deploy_helm_charts.sh"

# --- Utility Functions ---

# Prints a message in color
log() {
  echo -e "\n\e[1;32m$1\e[0m"
}

# Checks if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# --- Core Functions ---

# Checks for required dependencies (kubectl, helm)
check_deps() {
  log "Checking dependencies..."
  local missing_deps=0
  for cmd in kubectl helm k3sup; do
    if ! command_exists "$cmd"; then
      echo "Error: Command '$cmd' not found. Please install it first."
      missing_deps=1
    fi
  done

  if [ "$missing_deps" -eq 1 ]; then
    exit 1
  fi
  echo "All dependencies found."
}

# Deploys base Helm charts required by the IaC
deploy_helm_charts() {
  log "Deploying base Helm charts for metal environment..."
  if [ -f "$HELM_SCRIPT" ]; then
    chmod +x "$HELM_SCRIPT"
    if ./"$HELM_SCRIPT"; then
      echo "Base Helm charts deployed successfully."
    else
      echo "An error occurred during Helm chart deployment."
      exit 1
    fi
  else
    echo "Warning: Helm script '$HELM_SCRIPT' not found. Skipping step."
  fi
}

# Deploys the Kustomize overlay to the active cluster
deploy_iac() {
  log "Deploying IaC from Kustomize overlay '$KUSTOMIZE_OVERLAY_DIR'..."
  if kubectl apply -k "$KUSTOMIZE_OVERLAY_DIR"; then
    echo "IaC deployment completed."
  else
    echo "An error occurred during IaC deployment."
    exit 1
  fi
}

# Displays help information
show_help() {
  echo "Usage: $0 [command]"
  echo
  echo "Commands:"
  echo "  deploy    Deploys Helm charts and the full IaC overlay for metal."
  echo "  help      Displays this help message."
}


# --- Main Script Logic ---

case "$1" in
  deploy)
    check_deps
    deploy_helm_charts
    deploy_iac
    ;;
  help|*)
    show_help
    ;;
esac

log "Process finished."

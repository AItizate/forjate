#!/bin/bash

# This script automates the creation of a new application component.

# --- Configuration ---
COMPONENTS_DIR="k8s/components/apps"
# --- End Configuration ---

# --- Functions ---
function display_usage() {
  echo "Usage: $0 <app-name>"
  echo "Creates the basic structure for a new application component."
}

function create_directory_structure() {
  local app_name=$1
  local app_dir="${COMPONENTS_DIR}/${app_name}"

  if [ -d "${app_dir}" ]; then
    echo "Error: Directory '${app_dir}' already exists."
    exit 1
  fi

  echo "Creating directory: ${app_dir}"
  mkdir -p "${app_dir}"
}

function create_files() {
  local app_name=$1
  local app_dir="${COMPONENTS_DIR}/${app_name}"

  echo "Creating files in: ${app_dir}"
  touch "${app_dir}/deployment.yaml"
  touch "${app_dir}/service.yaml"
  touch "${app_dir}/ingress.yaml"
  touch "${app_dir}/kustomization.yaml"

  # Populate kustomization.yaml
  cat > "${app_dir}/kustomization.yaml" <<EOL
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - ingress.yaml
EOL
}

function main() {
  # Check if app name is provided
  if [ -z "$1" ]; then
    display_usage
    exit 1
  fi

  local app_name=$1

  create_directory_structure "${app_name}"
  create_files "${app_name}"

  echo "Successfully created component '${app_name}' in '${COMPONENTS_DIR}/${app_name}'"
  echo "Next steps:"
  echo "1. Edit the generated YAML files to define your application's resources."
  echo "2. Add the component to a tenant overlay's kustomization.yaml file."
}

# --- Main Execution ---
main "$@"

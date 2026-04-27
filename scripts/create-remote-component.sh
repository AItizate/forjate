#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Helper Functions ---
usage() {
  echo "Usage: $0 --category <category> --appName <app-name> --remoteUrl <remote-url>"
  echo "  --category     Category for the component (e.g., remote-apps)."
  echo "  --appName      Name of the application component (e.g., my-remote-app)."
  echo "  --remoteUrl    Full Kustomize URL to the remote component's base."
  echo "                 (e.g., https://github.com/sme/repo.git/k8s/base?ref=v1.0.0)"
  exit 1
}

log() {
  echo "[INFO] $1"
}

# --- Argument Parsing ---
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --category) category="$2"; shift ;;
    --appName) appName="$2"; shift ;;
    --remoteUrl) remoteUrl="$2"; shift ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

# Validate required arguments
if [ -z "$category" ] || [ -z "$appName" ] || [ -z "$remoteUrl" ]; then
  echo "Error: Missing required arguments."
  usage
fi

# --- Main Logic ---
targetDir="k8s/components/apps/$category/$appName"

log "Creating remote component stub '$appName' in category '$category'..."

# Check if component already exists
if [ -d "$targetDir" ]; then
  echo "Error: Component '$appName' already exists in category '$category' at '$targetDir'."
  exit 1
fi

# Create the directory and the kustomization.yaml file
log "Creating kustomization file at $targetDir/kustomization.yaml"
mkdir -p "$targetDir"

cat > "$targetDir/kustomization.yaml" << EOL
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - $remoteUrl
EOL

# Make the script executable
chmod +x "$0"

log "Remote component stub '$appName' created successfully in $targetDir!"

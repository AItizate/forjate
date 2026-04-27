#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Defaults ---
featureType="app"
createService=true
createIngress=true

# --- Helper Functions ---
usage() {
  echo "Usage: $0 --appName <app-name> --image <image-url> --port <port> [options]"
  echo "  --appName      Name of the application (e.g., my-cool-app)."
  echo "  --image        Full URL of the container image (e.g., my-repo/my-cool-app:latest)."
  echo "  --port         Container port."
  echo "  --hostname     Placeholder hostname for the ingress (e.g., my-app.example.com)."
  echo ""
  echo "Options:"
  echo "  --type         Type of the feature template to use (default: 'app')."
  echo "  --no-service   Flag to exclude the Service manifest."
  echo "  --no-ingress   Flag to exclude the Ingress manifest."
  exit 1
}

log() {
  echo "[INFO] $1"
}

# --- Argument Parsing ---
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --appName) appName="$2"; shift ;;
    --image) imageUrl="$2"; shift ;;
    --port) port="$2"; shift ;;
    --hostname) hostname="$2"; shift ;;
    --type) featureType="$2"; shift ;;
    --no-service) createService=false ;;
    --no-ingress) createIngress=false ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

# Validate required arguments
if [ -z "$appName" ] || [ -z "$imageUrl" ] || [ -z "$port" ]; then
  echo "Error: Missing required arguments."
  usage
fi

if [ "$createIngress" = true ] && [ -z "$hostname" ]; then
  echo "Error: --hostname is required unless --no-ingress is specified."
  usage
fi

# --- Main Logic ---
templateDir=".ait/templates/$featureType"
targetDir="k8s/base/apps/$appName"

log "Creating base feature '$appName' from template '$featureType'..."

# Check if template directory exists
if [ ! -d "$templateDir" ]; then
  echo "Error: Template type '$featureType' not found at '$templateDir'."
  exit 1
fi

# Copy templates to target directory
log "Copying templates to $targetDir..."
mkdir -p "$targetDir"
cp "$templateDir"/* "$targetDir/"

# Replace placeholders
log "Replacing placeholders in $targetDir..."
# Use a different delimiter for sed to avoid issues with image URLs
sed_delimiter="#"
for file in "$targetDir"/*; do
  sed -i '' -e "s${sed_delimiter}__APP_NAME__${sed_delimiter}$appName${sed_delimiter}g" "$file"
  sed -i '' -e "s${sed_delimiter}__IMAGE_URL__${sed_delimiter}$imageUrl${sed_delimiter}g" "$file"
  sed -i '' -e "s${sed_delimiter}__PORT__${sed_delimiter}$port${sed_delimiter}g" "$file"
  if [ -n "$hostname" ]; then
    sed -i '' -e "s${sed_delimiter}__HOSTNAME__${sed_delimiter}$hostname${sed_delimiter}g" "$file"
  fi
done

# Handle conditional files
kustomizationFile="$targetDir/kustomization.yaml"

if [ "$createService" = false ]; then
  log "Excluding Service..."
  rm "$targetDir/service.yaml"
  sed -i '' -e '/- service.yaml/d' "$kustomizationFile"
fi

if [ "$createIngress" = false ]; then
  log "Excluding Ingress..."
  rm "$targetDir/ingress.yaml"
  sed -i '' -e '/- ingress.yaml/d' "$kustomizationFile"
fi

log "Base feature '$appName' created successfully in $targetDir!"

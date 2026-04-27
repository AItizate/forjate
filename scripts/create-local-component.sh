#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Helper Functions ---
usage() {
  echo "Usage: $0 --category <category> --appName <app-name> --image <image-url> --port <port> --hostname <hostname>"
  echo "  --category     Category of the application (e.g., databases, monitoring)."
  echo "  --appName      Name of the application (e.g., my-cool-app)."
  echo "  --image        Full URL of the container image (e.g., my-repo/my-cool-app:latest)."
  echo "  --port         Container port."
  echo "  --hostname     Placeholder hostname for the ingress (e.g., my-app.example.com)."
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
    --image) imageUrl="$2"; shift ;;
    --port) port="$2"; shift ;;
    --hostname) hostname="$2"; shift ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

# Validate required arguments
if [ -z "$category" ] || [ -z "$appName" ] || [ -z "$imageUrl" ] || [ -z "$port" ] || [ -z "$hostname" ]; then
  echo "Error: Missing required arguments."
  usage
fi

# --- Main Logic ---
# Note: This script assumes it's run from the root of the 'forjate' repository.
templateDir=".ait/templates/local-component"
targetDir="k8s/components/apps/$category/$appName"

log "Creating local component '$appName' in category '$category'..."

# Check if component already exists
if [ -d "$targetDir" ]; then
  echo "Error: Component '$appName' already exists in category '$category' at '$targetDir'."
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
  # Use -i '' for macOS compatibility
  sed -i '' -e "s${sed_delimiter}__APP_NAME__${sed_delimiter}$appName${sed_delimiter}g" "$file"
  sed -i '' -e "s${sed_delimiter}__IMAGE_URL__${sed_delimiter}$imageUrl${sed_delimiter}g" "$file"
  sed -i '' -e "s${sed_delimiter}__PORT__${sed_delimiter}$port${sed_delimiter}g" "$file"
  sed -i '' -e "s${sed_delimiter}__HOSTNAME__${sed_delimiter}$hostname${sed_delimiter}g" "$file"
done

# Make the script executable
chmod +x "$0"

log "Local component '$appName' created successfully in $targetDir!"
log "Next step: Add it to a tenant overlay and patch the hostname."

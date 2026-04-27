#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Helper Functions ---

# Function to print usage information
usage() {
  echo "Usage: $0 --appName <app-name> --overlayName <overlay-name> --hostname <hostname>"
  echo "  --appName        Name of the application (must match the base app name)."
  echo "  --overlayName    Name of the overlay (tenant) to add the application to."
  echo "  --hostname       The tenant-specific hostname for the ingress."
  exit 1
}

# Function to log messages
log() {
  echo "[INFO] $1"
}

# --- Argument Parsing ---

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --appName) appName="$2"; shift ;;
    --overlayName) overlayName="$2"; shift ;;
    --hostname) hostname="$2"; shift ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

# Validate required arguments
if [ -z "$appName" ] || [ -z "$overlayName" ] || [ -z "$hostname" ]; then
  echo "Error: Missing required arguments."
  usage
fi

# --- Main Logic ---

overlayDir="k8s/overlays/$overlayName"
overlayKustomization="$overlayDir/kustomization.yaml"
appPatchDir="$overlayDir/apps/$appName"
ingressPatchFile="$appPatchDir/ingress-patch.yaml"

# Check if overlay exists
if [ ! -d "$overlayDir" ]; then
  echo "Error: Overlay '$overlayName' not found at '$overlayDir'."
  exit 1
fi

# --- Add Resource to Overlay ---

resourceEntry="- ../../base/apps/$appName"
log "Checking for resource in $overlayKustomization..."
if ! grep -q "$resourceEntry" "$overlayKustomization"; then
  log "Adding resource '$appName' to $overlayKustomization..."
  sed -i '' -e "/resources:/a\\
$resourceEntry" "$overlayKustomization"
else
  log "Resource '$appName' already exists in $overlayKustomization. Skipping."
fi

# --- Create Patch Directory and Files ---

log "Creating patch directory: $appPatchDir"
mkdir -p "$appPatchDir"

log "Generating Ingress patch: $ingressPatchFile"
cat > "$ingressPatchFile" << EOL
- op: replace
  path: /spec/rules/0/host
  value: $hostname
- op: replace
  path: /spec/tls/0/hosts/0
  value: $hostname
EOL

# --- Add Patch to Overlay ---

patchEntry="- path: apps/$appName/ingress-patch.yaml"
targetBlock="  target:\n    kind: Ingress\n    name: $appName"
fullPatchBlock="\n$patchEntry\n$targetBlock"

log "Checking for patch in $overlayKustomization..."
if ! grep -q "path: apps/$appName/ingress-patch.yaml" "$overlayKustomization"; then
  log "Adding Ingress patch for '$appName' to $overlayKustomization..."
  # Using awk to add the multi-line block after the 'patches:' line
  awk -v block="$fullPatchBlock" '/patches:/ { print; print block; next } 1' "$overlayKustomization" > tmp_kust.yaml && mv tmp_kust.yaml "$overlayKustomization"
else
  log "Ingress patch for '$appName' already exists in $overlayKustomization. Skipping."
fi

log "Application '$appName' successfully configured in overlay '$overlayName'!"

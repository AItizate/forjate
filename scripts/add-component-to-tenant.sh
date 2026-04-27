#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Helper Functions ---
usage() {
  echo "Usage: $0 --component <category/app-name> --tenant <tenant-name>"
  echo "  --component    Path to the component relative to 'k8s/components/apps/' (e.g., 'networking/whoami')."
  echo "  --tenant       Name of the tenant overlay (e.g., 'my-tenant')."
  exit 1
}

log() {
  echo "[INFO] $1"
}

# --- Argument Parsing ---
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --component) componentPath="$2"; shift ;;
    --tenant) tenantName="$2"; shift ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

# Validate required arguments
if [ -z "$componentPath" ] || [ -z "$tenantName" ]; then
  echo "Error: Missing required arguments."
  usage
fi

# --- Main Logic ---
appName=$(basename "$componentPath")
componentFullPath="k8s/components/apps/$componentPath"
tenantOverlayDir="k8s/overlays/$tenantName"
kustomizationFile="$tenantOverlayDir/kustomization.yaml"
patchesDir="$tenantOverlayDir/patches"

log "Adding component '$componentPath' to tenant '$tenantName'..."

# --- Validations ---
if [ ! -d "$componentFullPath" ]; then
  echo "Error: Component not found at '$componentFullPath'."
  exit 1
fi
if [ ! -d "$tenantOverlayDir" ]; then
  echo "Error: Tenant overlay not found at '$tenantOverlayDir'."
  exit 1
fi

# --- Add resource to kustomization.yaml ---
resourceLine="- ../../components/apps/$componentPath"
log "Adding resource to $kustomizationFile"

# Check if resource already exists
if grep -q "$resourceLine" "$kustomizationFile"; then
  echo "Warning: Component '$componentPath' is already present in the tenant's kustomization file. Skipping."
else
  # Use sed to add the resource line after the 'resources:' key.
  # This is a simple approach; for complex YAML, a proper parser like yq would be better.
  sed -i '' -e "/^resources:/a\\
  $resourceLine" "$kustomizationFile"
  log "Successfully added resource."
fi

# --- Create a placeholder ingress patch ---
patchFileName="$appName-ingress-patch.yaml"
patchFilePath="$patchesDir/$patchFileName"
log "Creating placeholder ingress patch at $patchFilePath..."

if [ -f "$patchFilePath" ]; then
  echo "Warning: Patch file '$patchFileName' already exists. Skipping."
else
  mkdir -p "$patchesDir"
  cat > "$patchFilePath" << EOL
# This is a placeholder patch.
# 1. Update the 'value' with the correct hostname for this tenant.
# 2. Uncomment the patch in the tenant's kustomization.yaml file.
- op: replace
  path: /spec/rules/0/host
  value: $appName.$tenantName
EOL
  log "Placeholder patch created."
fi

# Make the script executable
chmod +x "$0"

log "Component '$componentPath' added to tenant '$tenantName'."
log "ACTION REQUIRED: Edit the placeholder patch '$patchFilePath' and add it to the tenant's kustomization.yaml."

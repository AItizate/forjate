#!/bin/bash

# A simple script to recursively find and replace tenant name references in configuration files.
# This is useful when scaffolding a new tenant by copying an existing one.

# --- Configuration ---
OLD_TENANT=$1
NEW_TENANT=$2
TARGET_DIR="k8s/overlays/$NEW_TENANT"

# --- Validation ---
if [ -z "$OLD_TENANT" ] || [ -z "$NEW_TENANT" ]; then
  echo "Error: Missing arguments."
  echo "Usage: $0 <old_tenant_domain> <new_tenant_domain>"
  echo "Example: $0 old-tenant.example.com new-tenant.example.com"
  exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Target directory '$TARGET_DIR' does not exist."
  exit 1
fi

echo "--- Starting Tenant Rename ---"
echo "Old Tenant: $OLD_TENANT"
echo "New Tenant: $NEW_TENANT"
echo "Target Directory: $TARGET_DIR"
echo "------------------------------"

# --- Execution ---
# Use find to get all files in the target directory and pipe to xargs with sed.
# The `sed -i ''` command performs in-place editing without creating a backup file,
# which is compatible with both GNU and BSD (macOS) sed.
find "$TARGET_DIR" -type f -print0 | xargs -0 sed -i '' "s/$OLD_TENANT/$NEW_TENANT/g"

echo "Replacement complete. Please review the changes in the '$TARGET_DIR' directory."

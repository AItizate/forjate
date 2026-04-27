#!/bin/bash
set -e

echo ""
echo "Usage instructions:"
echo "   - These sealed secrets will respect the namespace set by Kustomize"
echo "   - Re-run this script anytime to regenerate and overwrite existing files"
echo "   - Make sure kubeseal is configured with the correct cluster context"
echo "   - Every time this process runs, will change encrypted values. It's fine"
# List overlays dynamically
echo ""
echo "Available overlays:"
select dir in k8s/overlays/*; do
    if [ -n "$dir" ]; then
        OVERLAY_DIR=$dir
        break
    fi
done

cd "$OVERLAY_DIR"
echo "Using overlay dir: $OVERLAY_DIR - Searching and converting .env files to sealed secrets..."

# Function to convert a .env file to sealed secret
convert_env_to_sealed() {
    local env_file=$1
    local dir=$(dirname "$env_file")
    local basename=$(basename "$env_file" .env)
    
    # Sealed secret name: sealed-{name}.yaml
    local output_file="$dir/sealed-${basename}.yaml"
    
    # Secret name in k8s: {name}
    local secret_name="${basename}"
    
    echo "  📝 $env_file -> $output_file (secret: $secret_name)"
    
    # Check if output file exists and notify about overwrite
    if [ -f "$output_file" ]; then
        echo "    ⚠️  File $output_file already exists - overwriting..."
    fi
    
    # Create temporary secret WITHOUT specific namespace
    kubectl create secret generic $secret_name \
        --from-env-file="$env_file" \
        --dry-run=client -o yaml > /tmp/temp-secret.yaml
    
    # Convert to sealed secret using cluster-wide scope (no fixed namespace)
    # Remove existing file first (since --force may not be available)
    if [ -f "$output_file" ]; then
        rm "$output_file"
    fi
    
    # Debug: Show the temp secret before sealing
    echo "    🔍 Debug - temp secret content:"
    cat /tmp/temp-secret.yaml | head -10
    
    kubeseal --scope cluster-wide -f /tmp/temp-secret.yaml -w "$output_file"
    
    # Clean up
    rm /tmp/temp-secret.yaml
    
    echo "    ✅ Successfully generated $output_file"
}

# Find all .env files
env_files_found=0
find . -name "*.env" -type f | while read env_file; do
    if [ -f "$env_file" ]; then
        echo "Found env file: $env_file"
        convert_env_to_sealed "$env_file"
        ((env_files_found++))
    fi
done

# Count and display generated sealed secrets
sealed_count=$(find . -name "sealed-*.yaml" -type f | wc -l)
echo ""
echo "📋 Generated sealed secrets ($sealed_count files):"
find . -name "sealed-*.yaml" -type f | sort
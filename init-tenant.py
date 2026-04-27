#!/usr/bin/env python3

import argparse
import os
import shutil
import yaml
from jinja2 import Environment, FileSystemLoader

def main():
    """
    Generates a new tenant IaC repository from the factory templates.
    """
    parser = argparse.ArgumentParser(description="Forjate Tenant Generator")
    parser.add_argument("config_file", type=str, help="Path to the tenant's YAML configuration file.")
    args = parser.parse_args()

    # --- 1. Load Configuration ---
    print(f"Parsing tenant configuration from {args.config_file}...")
    try:
        with open(args.config_file, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Tenant config file not found at {args.config_file}")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        exit(1)

    tenant_name = config.get("tenant", {}).get("name")
    tenant_domain = config.get("tenant", {}).get("domain")
    features = config.get("features", [])

    if not all([tenant_name, tenant_domain]):
        print("Error: 'tenant.name' and 'tenant.domain' must be defined in the config file.")
        exit(1)

    factory_dir = os.path.dirname(os.path.realpath(__file__))
    target_dir = os.path.join(os.path.dirname(factory_dir), f"{tenant_name}-iac")

    print(f"Tenant Name: {tenant_name}")
    print(f"Tenant Domain: {tenant_domain}")
    print(f"Target Directory: {target_dir}")
    print(f"Enabled Features: {', '.join(features)}")

    # --- 2. Define Ignore Patterns ---
    ignore_patterns = []
    ait_ignore_path = os.path.join(factory_dir, '.ait','.ignore')
    if os.path.exists(ait_ignore_path):
        with open(ait_ignore_path, 'r') as f:
            ignore_patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])

    # Add tenant-specific ignores
    tenant_specific_ignores = config.get("factory_settings", {}).get("exclude", [])
    ignore_patterns.extend(tenant_specific_ignores)
    
    # Always ignore the git directory and the config file itself
    ignore_patterns.extend(['.git', os.path.basename(args.config_file)])

    # --- 3. Create Tenant Directory and Copy Factory ---
    print(f"Creating new tenant directory at {target_dir}...")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    
    shutil.copytree(
        factory_dir, 
        target_dir, 
        ignore=shutil.ignore_patterns(*ignore_patterns)
    )

    # --- 3. Create Overlay ---
    overlay_dir = os.path.join(target_dir, "k8s", "overlays", "production")
    print(f"Creating production overlay at {overlay_dir}...")
    os.makedirs(overlay_dir, exist_ok=True)

    # --- 4. Create Overlay Kustomization ---
    print("Creating Kustomization for the production overlay...")
    kustomization_content = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "bases": ["../../base"],
        "resources": []
    }

    for feature in features:
        print(f"Enabling feature: {feature}")
        kustomization_content["resources"].append(f"../../base/apps/{feature}")

    with open(os.path.join(overlay_dir, "kustomization.yaml"), 'w') as f:
        yaml.dump(kustomization_content, f, sort_keys=False)

    # --- 5. Generate Readme ---
    print("Generating README.md for the new tenant...")
    
    # Setup Jinja2 environment
    template_dir = os.path.join(factory_dir, '.ait','templates', 'docs')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('README.md')

    # Prepare features list for the template
    features_list_str = "\n".join([f"    - `{feature}.{tenant_domain}` (Example URL, please check ingress files for actual hostnames)" for feature in features])

    readme_content = template.render(
        TENANT_NAME=tenant_name,
        TENANT_DOMAIN=tenant_domain,
        FEATURES_LIST=features_list_str
    )
    
    with open(os.path.join(target_dir, "README.md"), 'w') as f:
        f.write(readme_content)

    # --- 6. Cleanup ---
    # The ignore logic should handle all cleanup implicitly. 
    # This section can be removed or used for post-generation tasks if needed.
    # For now, we will remove the template directory that gets copied over.
    template_dir_in_target = os.path.join(target_dir, '.ait', 'templates')
    if os.path.exists(template_dir_in_target):
        shutil.rmtree(template_dir_in_target)
    
    print(f"\nTenant IaC generated successfully at {target_dir}")


if __name__ == "__main__":
    main()

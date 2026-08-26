#!/usr/bin/env bash
# =============================================================================
# create-usecase.sh — Scaffold a new ephemeral use-case environment.
#
# Produces a complete, runnable skeleton under k8s/overlays/usecases/<name>/:
# contract, kustomizations, namespace, stub seed/run/verify Jobs, README and
# .gitignore. Wire in the catalog components you need, fill the Jobs, done.
#
# Usage: ./create-usecase.sh --name <name> [--isolation shared|dedicated]
#                            [--ttl 4h] [--prefix <job-prefix>]
#
# Design: docs/ephemeral-use-cases.md
# =============================================================================

# shellcheck source-path=SCRIPTDIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_DIR="${REPO_ROOT}/.ait/templates/usecase"
UC_ROOT="${REPO_ROOT}/k8s/overlays/usecases"

# shellcheck source=lib/log.sh
source "${SCRIPT_DIR}/lib/log.sh"

usage() {
  cat <<'EOF'
Usage: ./create-usecase.sh --name <name> [options]

  --name <name>          Use-case name (lowercase, dashes). Becomes the
                         directory name and the namespace suffix.
  --isolation <mode>     shared (default) | dedicated. Choose dedicated when
                         the use case installs CRDs, operators or
                         StorageClasses — those outlive namespace deletion.
  --ttl <duration>       How long before gc reclaims it. Default: 4h.
  --prefix <prefix>      Prefix for the three Job names. Default: the use-case
                         name. Use a short one when the name is long.

Example:
  ./create-usecase.sh --name doc-ingestion --ttl 2h --prefix docing
EOF
  exit 1
}

# ── Arguments ────────────────────────────────────────────────────────────────

name=""; isolation="shared"; ttl="4h"; prefix=""

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --name)      name="${2:-}"; shift ;;
    --isolation) isolation="${2:-}"; shift ;;
    --ttl)       ttl="${2:-}"; shift ;;
    --prefix)    prefix="${2:-}"; shift ;;
    -h|--help)   usage ;;
    *) echo "Unknown parameter: $1" >&2; usage ;;
  esac
  shift
done

[ -n "$name" ] || { echo "Error: --name is required" >&2; usage; }
prefix="${prefix:-$name}"

echo "$name" | grep -qE '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$' \
  || error "Invalid name '${name}' — lowercase letters, digits and dashes only"
echo "$prefix" | grep -qE '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$' \
  || error "Invalid prefix '${prefix}' — lowercase letters, digits and dashes only"
echo "$ttl" | grep -qE '^[1-9][0-9]*[mhd]$' \
  || error "Invalid ttl '${ttl}' — expected <N>m, <N>h or <N>d"
case "$isolation" in
  shared|dedicated) ;;
  *) error "Invalid isolation '${isolation}' — expected shared or dedicated" ;;
esac

namespace="uc-${name}"
target="${UC_ROOT}/${name}"

[ -d "$TEMPLATE_DIR" ] || error "Templates not found at ${TEMPLATE_DIR}"
[ -e "$target" ] && error "Use case '${name}' already exists at ${target}"

# ── Scaffold ─────────────────────────────────────────────────────────────────

info "Scaffolding use case '${name}' (${isolation}, ttl ${ttl})..."

mkdir -p "$target"
cp -R "${TEMPLATE_DIR}/." "$target/"

# Placeholders appear in both file contents and path components.
find "$target" -depth -name '*__*__*' | while IFS= read -r path; do
  base="$(basename "$path")"
  renamed="${base//__NAMESPACE__/$namespace}"
  renamed="${renamed//__PREFIX__/$prefix}"
  renamed="${renamed//__NAME__/$name}"
  [ "$base" = "$renamed" ] || mv "$path" "$(dirname "$path")/${renamed}"
done

while IFS= read -r file; do
  sed -i.bak \
    -e "s|__NAMESPACE__|${namespace}|g" \
    -e "s|__PREFIX__|${prefix}|g" \
    -e "s|__ISOLATION__|${isolation}|g" \
    -e "s|__TTL__|${ttl}|g" \
    -e "s|__NAME__|${name}|g" \
    "$file"
  rm -f "${file}.bak"
done < <(find "$target" -type f)

mkdir -p "${target}/namespaces/${namespace}/secrets" "${target}/namespaces/${namespace}/patches"

log "Created ${target#"${REPO_ROOT}/"}"

cat <<EOF

Next steps:

  1. Add the catalog components you need to
     k8s/overlays/usecases/${name}/namespaces/${namespace}/kustomization.yaml
     (paths are relative: ../../../../../components/apps/<category>/<name>)

  2. Declare their credentials as secretGenerator entries and commit a
     matching secrets/<component>.env.example for each one.

  3. Fill the three Jobs and update spec.outputs in usecase.yaml so agents
     know what this environment exposes.

  4. Run it:
       ./scripts/ephemeral/ephemeral.sh up ${name}
EOF

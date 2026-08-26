#!/usr/bin/env bash
# =============================================================================
# deps.sh — Dependency preflight for the ephemeral use-case runner.
#
# Source this file; do not execute it. Requires log.sh to be sourced first.
# =============================================================================

# Install hints, printed only for the commands that are actually missing.
_dep_hint() {
  case "$1" in
    k3d)       echo "  k3d:       brew install k3d          — https://k3d.io/#installation" ;;
    kubectl)   echo "  kubectl:   brew install kubectl       — https://kubernetes.io/docs/tasks/tools/" ;;
    kustomize) echo "  kustomize: brew install kustomize     — https://kubectl.docs.kubernetes.io/installation/kustomize/" ;;
    yq)        echo "  yq:        brew install yq            — https://github.com/mikefarah/yq (v4+)" ;;
    docker)    echo "  docker:    https://docs.docker.com/get-docker/" ;;
    *)         echo "  $1: (no install hint available)" ;;
  esac
}

# require_cmds <cmd>... — fail with a combined install hint if any are missing.
require_cmds() {
  local missing=() cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done

  if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing required commands: ${missing[*]}" >&2
    echo "" >&2
    echo "Install:" >&2
    for cmd in "${missing[@]}"; do _dep_hint "$cmd" >&2; done
    exit 1
  fi
}

# yq must be mikefarah/yq v4+ — the python yq has an incompatible CLI.
require_yq_v4() {
  if ! yq --version 2>&1 | grep -qE 'v?4\.'; then
    error "yq v4 (mikefarah) is required. Found: $(yq --version 2>&1). Install with: brew install yq"
  fi
}

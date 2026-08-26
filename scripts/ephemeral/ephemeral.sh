#!/usr/bin/env bash
# =============================================================================
# ephemeral.sh — Runner for ephemeral use-case environments.
#
# One command per lifecycle phase, for every use case under
# k8s/overlays/usecases/. Each use case declares what it is in a usecase.yaml
# contract; this script is entirely generic.
#
# Usage: ./ephemeral.sh <command> [use-case] [flags]
# Run './ephemeral.sh help' for the full reference.
#
# Design: see docs/ephemeral-use-cases.md
# =============================================================================

# shellcheck source-path=SCRIPTDIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# Read by lib/usecase.sh to resolve use-case directories.
UC_ROOT="${REPO_ROOT}/k8s/overlays/usecases"

# shellcheck source=lib/log.sh
source "${SCRIPT_DIR}/lib/log.sh"
# shellcheck source=lib/deps.sh
source "${SCRIPT_DIR}/lib/deps.sh"
# shellcheck source=lib/cluster.sh
source "${SCRIPT_DIR}/lib/cluster.sh"
# shellcheck source=lib/usecase.sh
source "${SCRIPT_DIR}/lib/usecase.sh"
# shellcheck source=lib/job.sh
source "${SCRIPT_DIR}/lib/job.sh"

# ── Helpers ──────────────────────────────────────────────────────────────────

# Prefer standalone kustomize; fall back to the copy embedded in kubectl.
kustomize_build() {
  if command -v kustomize >/dev/null 2>&1; then
    kustomize build "$1"
  else
    kubectl kustomize "$1"
  fi
}

# Seed gitignored .env files from their committed examples, the same way CI
# does, so a fresh clone can run without hand-copying placeholder secrets.
seed_env_files() {
  local dir="$1" example real
  while IFS= read -r example; do
    real="${example%.example}"
    if [ ! -f "$real" ]; then
      cp "$example" "$real"
      info "Seeded $(basename "$real") from its example"
    fi
  done < <(find "$dir" -type f -name '*.env.example')
}

# Namespaces in the current cluster that this runner manages.
managed_namespaces() {
  kubectl get ns -l "$UC_LABEL_MANAGED" \
    -o jsonpath="{range .items[*]}{.metadata.name}{'\t'}{.metadata.labels.${UC_LABEL_NAME//./\\.}}{'\t'}{.metadata.annotations.${UC_ANNOTATION_EXPIRES//./\\.}}{'\n'}{end}" \
    2>/dev/null || true
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_up() {
  local name="${1:?use case name required}"
  require_cmds k3d kubectl yq docker
  require_yq_v4
  uc_require "$name"

  local isolation ttl cluster ns dir manifest
  isolation="$(uc_get "$name" '.spec.isolation')"
  ttl="$(uc_get "$name" '.spec.ttl')"
  cluster="$(cluster_name_for "$name" "$isolation")"
  ns="$(uc_namespace "$name")"
  dir="$(uc_dir "$name")"

  section "Cluster (${isolation})"
  ensure_cluster "$cluster"

  section "Overlay"
  seed_env_files "$dir"

  manifest="$(mktemp -t forjate-uc-XXXXXX)"
  # shellcheck disable=SC2064  # expand $manifest now, not at trap time
  trap "rm -f '$manifest'" EXIT
  kustomize_build "$dir" > "$manifest"
  log "Built $(grep -c '^kind:' "$manifest") resources"

  # Jobs are immutable. A previous run leaves them behind, so applying an
  # overlay whose Job specs changed would fail on the whole manifest — clear
  # them first. run_job deletes again before each phase, which is what makes
  # the seed/validate subcommands work on their own.
  local phase job
  for phase in seed run verify; do
    job="$(uc_job_name "$name" "$phase")"
    [ -n "$job" ] || continue
    kubectl -n "$ns" delete job "$job" --ignore-not-found --wait >/dev/null 2>&1 || true
  done

  # Two passes: the first establishes CRDs and namespaces, the second
  # reconciles resources that depend on them.
  if ! kubectl apply -f "$manifest" >/dev/null 2>&1; then
    info "First apply incomplete (CRD establishment) — retrying..."
    sleep 3
    kubectl apply -f "$manifest" >/dev/null
  else
    sleep 3
    kubectl apply -f "$manifest" >/dev/null
  fi
  log "Overlay applied to namespace ${ns}"

  # Stamp ownership and expiry so `ls` and `gc` need no local state file.
  local expires
  expires="$(rfc3339_at "$(ttl_to_seconds "$ttl")")"
  kubectl label ns "$ns" "$UC_LABEL_MANAGED" "${UC_LABEL_NAME}=${name}" --overwrite >/dev/null
  kubectl annotate ns "$ns" "${UC_ANNOTATION_EXPIRES}=${expires}" --overwrite >/dev/null
  log "Expires at ${expires} (ttl ${ttl})"

  section "Lifecycle"
  for phase in seed run verify; do
    job="$(uc_job_name "$name" "$phase")"
    if [ -z "$job" ]; then
      if [ "$phase" = "run" ]; then
        info "No 'run' Job declared — skipping"
        continue
      fi
      error "Missing required '${phase}' Job in the contract"
    fi
    run_job "$ns" "$job" "$(uc_job_timeout "$name" "$phase")" "$manifest" \
      || error "Use case '${name}' failed at the '${phase}' phase"
  done

  section "Ready"
  log "Use case '${name}' is up and validated"
  uc_print_outputs "$name"
  echo ""
  echo "  kubectl --kubeconfig $(kubeconfig_path "$cluster") -n ${ns} get pods"
  echo "  ./scripts/ephemeral/ephemeral.sh down ${name}"
}

# Re-run a single lifecycle Job against a live environment.
cmd_run_phase() {
  local phase="$1" name="${2:?use case name required}"
  require_cmds k3d kubectl yq
  require_yq_v4
  uc_require "$name"

  local isolation cluster ns job manifest
  isolation="$(uc_get "$name" '.spec.isolation')"
  cluster="$(cluster_name_for "$name" "$isolation")"
  ns="$(uc_namespace "$name")"
  job="$(uc_job_name "$name" "$phase")"

  [ -n "$job" ] || error "No '${phase}' Job declared in the contract for '${name}'"
  use_cluster "$cluster"

  manifest="$(mktemp -t forjate-uc-XXXXXX)"
  # shellcheck disable=SC2064
  trap "rm -f '$manifest'" EXIT
  kustomize_build "$(uc_dir "$name")" > "$manifest"

  run_job "$ns" "$job" "$(uc_job_timeout "$name" "$phase")" "$manifest" \
    || error "Job '${job}' did not complete"
}

cmd_down() {
  local name="${1:?use case name required}"
  require_cmds k3d kubectl yq
  uc_require "$name"

  local isolation cluster ns
  isolation="$(uc_get "$name" '.spec.isolation')"
  cluster="$(cluster_name_for "$name" "$isolation")"
  ns="$(uc_namespace "$name")"

  if [ "$isolation" = "dedicated" ]; then
    delete_cluster "$cluster"
  else
    if ! cluster_exists "$cluster"; then
      warn "Shared cluster '${cluster}' does not exist — nothing to tear down"
      return 0
    fi
    use_cluster "$cluster"
    info "Deleting namespace ${ns}..."
    kubectl delete ns "$ns" --ignore-not-found --wait >/dev/null
    log "Namespace ${ns} deleted (shared cluster '${cluster}' kept)"
  fi
}

cmd_ls() {
  require_cmds k3d kubectl yq docker
  printf '%-28s %-10s %-32s %-10s %s\n' "USE CASE" "ISOLATION" "CLUSTER" "STATUS" "EXPIRES IN"

  # Shared: one row per managed namespace on the shared cluster.
  if cluster_exists "$UC_SHARED_CLUSTER"; then
    use_cluster "$UC_SHARED_CLUSTER"
    while IFS=$'\t' read -r _ uc_name expires; do
      [ -n "${uc_name:-}" ] || continue
      local epoch remaining
      epoch="$(epoch_from_rfc3339 "$expires")"
      remaining="${epoch:+$(humanize_remaining "$epoch")}"
      printf '%-28s %-10s %-32s %-10s %s\n' \
        "$uc_name" "shared" "$UC_SHARED_CLUSTER" "running" "${remaining:-unknown}"
    done < <(managed_namespaces)
  fi

  # Dedicated: one row per ephemeral cluster.
  local cluster uc_name created epoch ttl remaining
  while IFS= read -r cluster; do
    [ -n "$cluster" ] || continue
    uc_name="${cluster#"$UC_CLUSTER_PREFIX"}"
    created="$(cluster_created_at "$cluster")"
    epoch="$(epoch_from_rfc3339 "$created")"
    remaining="unknown"
    if [ -n "$epoch" ] && [ -f "$(uc_file "$uc_name")" ]; then
      ttl="$(uc_get "$uc_name" '.spec.ttl' '4h')"
      remaining="$(humanize_remaining $(( epoch + $(ttl_to_seconds "$ttl") )))"
    fi
    printf '%-28s %-10s %-32s %-10s %s\n' \
      "$uc_name" "dedicated" "$cluster" "running" "$remaining"
  done < <(list_uc_clusters)
}

cmd_gc() {
  local dry_run="${1:-}"
  require_cmds k3d kubectl yq docker
  local now reclaimed=0
  now="$(now_epoch)"

  [ "$dry_run" = "--dry-run" ] && info "Dry run — nothing will be deleted"

  # Shared: expired namespaces.
  if cluster_exists "$UC_SHARED_CLUSTER"; then
    use_cluster "$UC_SHARED_CLUSTER"
    while IFS=$'\t' read -r ns uc_name expires; do
      [ -n "${ns:-}" ] || continue
      local epoch
      epoch="$(epoch_from_rfc3339 "$expires")"
      if [ -z "$epoch" ]; then
        warn "Namespace ${ns} has no readable ${UC_ANNOTATION_EXPIRES} — skipping"
        continue
      fi
      if [ "$epoch" -lt "$now" ]; then
        reclaimed=$(( reclaimed + 1 ))
        if [ "$dry_run" = "--dry-run" ]; then
          echo "  would delete namespace ${ns} (use case ${uc_name}, expired ${expires})"
        else
          info "Deleting expired namespace ${ns} (use case ${uc_name})"
          kubectl delete ns "$ns" --ignore-not-found --wait >/dev/null
        fi
      fi
    done < <(managed_namespaces)
  fi

  # Dedicated: clusters older than their contract's ttl.
  local cluster uc_name created epoch ttl
  while IFS= read -r cluster; do
    [ -n "$cluster" ] || continue
    uc_name="${cluster#"$UC_CLUSTER_PREFIX"}"
    if [ ! -f "$(uc_file "$uc_name")" ]; then
      warn "Cluster ${cluster} has no matching use case contract — skipping"
      continue
    fi
    created="$(cluster_created_at "$cluster")"
    epoch="$(epoch_from_rfc3339 "$created")"
    [ -n "$epoch" ] || { warn "Cannot read creation time for ${cluster} — skipping"; continue; }

    ttl="$(uc_get "$uc_name" '.spec.ttl' '4h')"
    if [ $(( epoch + $(ttl_to_seconds "$ttl") )) -lt "$now" ]; then
      reclaimed=$(( reclaimed + 1 ))
      if [ "$dry_run" = "--dry-run" ]; then
        echo "  would delete cluster ${cluster} (use case ${uc_name}, ttl ${ttl})"
      else
        delete_cluster "$cluster"
      fi
    fi
  done < <(list_uc_clusters)

  if [ "$reclaimed" -eq 0 ]; then
    log "Nothing to reclaim"
  else
    log "${reclaimed} environment(s) $([ "$dry_run" = "--dry-run" ] && echo "would be" || echo "were") reclaimed"
  fi
}

show_help() {
  cat <<'EOF'
ephemeral.sh — runner for ephemeral use-case environments

Usage:
  ./ephemeral.sh up <use-case>          Bring the environment up and validate it
  ./ephemeral.sh seed <use-case>        Re-run only the seed Job
  ./ephemeral.sh validate <use-case>    Re-run only the verify Job
  ./ephemeral.sh down <use-case>        Tear the environment down
  ./ephemeral.sh ls                     List live environments and time remaining
  ./ephemeral.sh gc [--dry-run]         Reclaim environments past their TTL
  ./ephemeral.sh help                   This message

`up` is idempotent: it redeploys the overlay and re-runs seed -> run -> verify.
It blocks until the verify Job exits 0, so a zero exit status means the
environment is genuinely ready to use.

Use cases live in k8s/overlays/usecases/<name>/ and declare themselves in a
usecase.yaml contract. Create one with:

  ./scripts/ephemeral/create-usecase.sh --name my-use-case

Env:
  K3D_IMAGE           k3s image for new clusters (default: rancher/k3s:v1.31.3-k3s1)
  UC_SHARED_CLUSTER   name of the shared cluster (default: forjate-uc-shared)

Requires: k3d, kubectl, yq (v4), docker. kustomize is used when present,
otherwise `kubectl kustomize`.

Design: docs/ephemeral-use-cases.md
EOF
}

# ── Dispatch ─────────────────────────────────────────────────────────────────

case "${1:-help}" in
  up)       cmd_up "${2:-}" ;;
  seed)     cmd_run_phase seed "${2:-}" ;;
  validate) cmd_run_phase verify "${2:-}" ;;
  down)     cmd_down "${2:-}" ;;
  ls)       cmd_ls ;;
  gc)       cmd_gc "${2:-}" ;;
  help|-h|--help) show_help ;;
  *)
    echo "Unknown command: $1" >&2
    echo "" >&2
    show_help >&2
    exit 2
    ;;
esac

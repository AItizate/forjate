#!/usr/bin/env bash
# =============================================================================
# job.sh — Lifecycle Job execution for ephemeral use-case environments.
#
# Source this file; do not execute it. Requires log.sh to be sourced first.
#
# Use-case Jobs ship with `spec.suspend: true` so that applying the overlay
# creates them without starting them — the runner is what decides the order
# (seed → run → verify). This function un-suspends one Job at a time.
#
# Jobs are immutable, so a re-run deletes before applying. The manifest is
# extracted from the already-built overlay rather than read from a file, which
# keeps a single source of truth: what CI validates is what runs.
# =============================================================================

# run_job <namespace> <job-name> <timeout-seconds> <built-manifest>
# Returns 0 when the Job completes, 1 on failure or timeout. Logs are always
# printed, whichever way it goes.
run_job() {
  local ns="$1" job="$2" timeout="$3" manifest="$4"
  local job_yaml status

  # `yq ea` collects every document into one stream before filtering, then the
  # array wrapper picks the single match. A bare `select(...)` per document
  # behaves differently across yq 4.x releases — older ones apply the trailing
  # expression to non-matching documents too, which yields the whole manifest
  # instead of one Job.
  job_yaml="$(yq ea "[select(.kind == \"Job\" and .metadata.name == \"${job}\")] | .[0] | .spec.suspend = false" \
                 "$manifest" 2>/dev/null)"

  if [ -z "$(echo "$job_yaml" | tr -d '[:space:]-')" ]; then
    warn "Job '${job}' not found in the built manifest — skipping"
    return 1
  fi

  info "Running Job/${job} (timeout: ${timeout}s)..."

  # Jobs are immutable: a previous run must be gone before re-applying.
  kubectl -n "$ns" delete job "$job" --ignore-not-found --wait >/dev/null 2>&1 || true
  echo "$job_yaml" | kubectl -n "$ns" apply -f - >/dev/null

  # Poll for either terminal condition rather than `kubectl wait --for=complete`:
  # that only unblocks on success, so a Job that fails immediately would still
  # burn the entire timeout before being reported. Conditions are read by .type
  # because kubectl 1.36+ adds SuccessCriteriaMet alongside Complete.
  local deadline=$(( SECONDS + timeout )) conditions
  status="Timeout"
  while [ "$SECONDS" -lt "$deadline" ]; do
    conditions="$(kubectl -n "$ns" get "job/${job}" -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}' 2>/dev/null || echo "")"
    case "$conditions" in
      *"Complete=True"*) status="Complete"; break ;;
      *"Failed=True"*)   status="Failed";   break ;;
    esac
    sleep 2
  done

  echo ""
  echo "─── ${job} logs ────────────────────────────────────────────"
  kubectl -n "$ns" logs "job/${job}" --tail=200 2>/dev/null || true
  rule
  echo ""

  case "$status" in
    Complete) log "Job/${job} completed"; return 0 ;;
    Failed)   warn "Job/${job} failed";   return 1 ;;
    *)        warn "Job/${job} timed out after ${timeout}s"; return 1 ;;
  esac
}

#!/usr/bin/env bash
# =============================================================================
# health.sh — Health signals of a use case that has just passed its verify Job.
#
# Source this file; do not execute it. Requires log.sh and usecase.sh first.
#
# A verify Job that exits 0 proves the use case did its work once. Two things it
# cannot show, and which the nightly (#21) is the first to see:
#
#   restarts   a pod that restarted after the verify is a probe or a crash the
#              verify did not touch (the replay that raced a stub still starting
#              looked healthy once and flaked the next night). Expected: 0.
#   kpi        the KPI/EVAL lines of the verify log on a second `up` of the same
#              seed. A threshold that passes by timing or by luck moves.
#              Expected: equal.
#
# Both are printed as `HEALTH key=value` lines, which the nightly greps and
# asserts. `up --stability` makes the runner assert them itself. A restart also prints `DIAG` blocks (describe and
# previous logs of the restarted pod) so a red nightly names its cause.
# =============================================================================

HEALTH_RESTARTS=0
HEALTH_KPIS=""

# health_restart_rows <namespace> — "<pod>\t<restarts>" for every pod whose containers restarted.
health_restart_rows() {
  kubectl -n "$1" get pods -o \
    jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.restartCount}{" "}{end}{range .status.initContainerStatuses[*]}{.restartCount}{" "}{end}{"\n"}{end}' \
    2>/dev/null \
    | awk -F'\t' 'NF >= 2 { n = 0; c = split($2, a, " "); for (i = 1; i <= c; i++) n += a[i]; if (n > 0) printf "%s\t%d\n", $1, n }'
}

# health_kpis <namespace> <verify-job> — the job log's KPI/EVAL lines as "KPI name=value", sorted.
health_kpis() {
  local ns="$1" job="$2"
  [ -n "$job" ] || return 0
  kubectl -n "$ns" logs "job/${job}" 2>/dev/null \
    | sed -nE 's/^[[:space:]]*(KPI|EVAL)[[:space:]]+([A-Za-z0-9_]+=[^[:space:]]+).*/\1 \2/p' \
    | sort
}

# health_restart_diagnostics <namespace> <pod> — why a pod restarted: `describe pod` (Last State, reason, exit
# code, probes, events) and the previous log of every container that restarted. The Environment block is dropped
# from the describe: literal env values are credentials in some use cases and this output lands in CI logs.
health_restart_diagnostics() {
  local ns="$1" pod="$2" container
  echo "DIAG describe pod ${pod}"
  kubectl -n "$ns" describe pod "$pod" 2>&1 \
    | awk '/^ +Environment:/ { match($0, /^ +/); skip = RLENGTH; next } skip && match($0, /^ */) && RLENGTH > skip { next } { skip = 0; print }' || true
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    echo "DIAG previous logs ${pod}/${container}"
    kubectl -n "$ns" logs "$pod" -c "$container" --previous --tail=100 2>&1 || true
  done < <(kubectl -n "$ns" get pod "$pod" -o \
    jsonpath='{range .status.containerStatuses[?(@.restartCount>0)]}{.name}{"\n"}{end}{range .status.initContainerStatuses[?(@.restartCount>0)]}{.name}{"\n"}{end}' 2>/dev/null || true)
}

# record_health <use-case> <namespace> — print the HEALTH lines; sets HEALTH_RESTARTS and HEALTH_KPIS.
record_health() {
  local name="$1" ns="$2" rows pod n
  rows="$(health_restart_rows "$ns" || true)"
  HEALTH_RESTARTS="$(printf '%s' "$rows" | awk -F'\t' '{ n += $2 } END { print n + 0 }')"
  echo "HEALTH pod_restarts_after_verify=${HEALTH_RESTARTS}"
  while IFS=$'\t' read -r pod n; do
    [ -n "$pod" ] && echo "HEALTH restarted_pod=${pod} restarts=${n}"
  done <<< "$rows"
  while IFS=$'\t' read -r pod n; do
    [ -n "$pod" ] && health_restart_diagnostics "$ns" "$pod"
  done <<< "$rows"
  HEALTH_KPIS="$(health_kpis "$ns" "$(uc_job_name "$name" verify)" || true)"
  echo "HEALTH kpi_lines=$(printf '%s' "$HEALTH_KPIS" | grep -c . || true)"
  return 0
}

# compare_kpis <first> <second> — prints HEALTH kpi_second_up=equal|differs|unmeasured; returns 1 on differs.
compare_kpis() {
  local first="$1" second="$2"
  if [ -z "$first" ] && [ -z "$second" ]; then
    echo "HEALTH kpi_second_up=unmeasured"
    return 0
  fi
  if [ "$first" = "$second" ]; then
    echo "HEALTH kpi_second_up=equal"
    return 0
  fi
  echo "HEALTH kpi_second_up=differs"
  diff <(printf '%s\n' "$first") <(printf '%s\n' "$second") | sed -n 's/^[<>] /HEALTH kpi_diff &/p' || true
  return 1
}

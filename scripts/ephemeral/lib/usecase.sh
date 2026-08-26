#!/usr/bin/env bash
# =============================================================================
# usecase.sh — usecase.yaml contract parsing and TTL arithmetic.
#
# Source this file; do not execute it. Requires log.sh to be sourced first.
# Expects UC_ROOT to point at k8s/overlays/usecases.
# =============================================================================

UC_LABEL_MANAGED="app.kubernetes.io/managed-by=forjate-ephemeral"
UC_LABEL_NAME="forjate.io/usecase"
UC_ANNOTATION_EXPIRES="forjate.io/expires-at"

# ── Paths ────────────────────────────────────────────────────────────────────

uc_dir()       { echo "${UC_ROOT}/$1"; }
uc_file()      { echo "${UC_ROOT}/$1/usecase.yaml"; }
uc_namespace() { echo "uc-$1"; }

# uc_list — every directory under UC_ROOT that carries a contract.
uc_list() {
  [ -d "$UC_ROOT" ] || return 0
  find "$UC_ROOT" -mindepth 2 -maxdepth 2 -name usecase.yaml -exec dirname {} \; \
    | xargs -n1 basename 2>/dev/null | sort
}

# ── Contract access ──────────────────────────────────────────────────────────

# uc_get <name> <yq-expression> [default] — read one field from the contract.
uc_get() {
  local name="$1" expr="$2" default="${3:-}" value
  value="$(yq -r "${expr} // \"\"" "$(uc_file "$name")" 2>/dev/null || echo "")"
  if [ -z "$value" ] || [ "$value" = "null" ]; then
    echo "$default"
  else
    echo "$value"
  fi
}

# uc_require <name> — assert the contract exists and is internally consistent.
uc_require() {
  local name="$1" file declared
  file="$(uc_file "$name")"

  [ -f "$file" ] || error "No use case '${name}' — expected contract at ${file}"

  declared="$(uc_get "$name" '.metadata.name')"
  [ "$declared" = "$name" ] || \
    error "Contract mismatch: metadata.name is '${declared}' but the directory is '${name}'"

  local isolation
  isolation="$(uc_get "$name" '.spec.isolation')"
  case "$isolation" in
    shared|dedicated) ;;
    *) error "Invalid spec.isolation '${isolation}' in ${file} (expected: shared | dedicated)" ;;
  esac

  [ -n "$(uc_get "$name" '.spec.ttl')" ] || error "Missing spec.ttl in ${file}"
  [ -n "$(uc_get "$name" '.spec.jobs.seed.name')" ]   || error "Missing spec.jobs.seed.name in ${file}"
  [ -n "$(uc_get "$name" '.spec.jobs.verify.name')" ] || error "Missing spec.jobs.verify.name in ${file}"
}

# uc_job_name <name> <phase> — Job name for seed | run | verify ("" if absent).
uc_job_name() { uc_get "$1" ".spec.jobs.$2.name"; }

# uc_job_timeout <name> <phase> — timeout in seconds (default 300).
uc_job_timeout() { uc_get "$1" ".spec.jobs.$2.timeout" "300"; }

# uc_print_outputs <name> — the agent-facing summary: resolved endpoints and
# the Secrets holding their credentials.
uc_print_outputs() {
  local name="$1" ns
  ns="$(uc_namespace "$name")"

  echo ""
  echo "Endpoints (in-cluster):"
  yq -r '.spec.outputs.endpoints[]? | "  \(.name): \(.service) \(.port) \(.protocol // "")"' \
    "$(uc_file "$name")" 2>/dev/null \
    | while read -r label svc port proto; do
        printf '  %-10s %s.%s.svc.cluster.local:%s %s\n' \
          "${label}" "${svc}" "${ns}" "${port}" "${proto}"
      done

  echo ""
  echo "Credentials (Secrets in namespace ${ns}):"
  yq -r '.spec.outputs.secrets[]? | "  \(.name) -> \(.secretRef)"' \
    "$(uc_file "$name")" 2>/dev/null || true
}

# ── TTL arithmetic ───────────────────────────────────────────────────────────

# ttl_to_seconds <ttl> — parse 30m | 4h | 2d into seconds.
ttl_to_seconds() {
  local ttl="$1" value unit
  value="${ttl%[mhd]}"
  unit="${ttl##*[0-9]}"

  case "$unit" in
    m) echo $(( value * 60 )) ;;
    h) echo $(( value * 3600 )) ;;
    d) echo $(( value * 86400 )) ;;
    *) error "Invalid ttl '${ttl}' (expected <N>m, <N>h or <N>d)" ;;
  esac
}

# rfc3339_at <offset-seconds> — timestamp N seconds from now, UTC.
# BSD date (macOS, the primary target) and GNU date (CI) disagree on flags.
rfc3339_at() {
  local offset="$1"
  if date -u -v "+${offset}S" '+%Y-%m-%dT%H:%M:%SZ' >/dev/null 2>&1; then
    date -u -v "+${offset}S" '+%Y-%m-%dT%H:%M:%SZ'
  else
    date -u -d "+${offset} seconds" '+%Y-%m-%dT%H:%M:%SZ'
  fi
}

# epoch_from_rfc3339 <timestamp> — parse to epoch seconds ("" when unparseable).
# Fractional seconds (docker's .Created carries nanoseconds) are stripped.
epoch_from_rfc3339() {
  local ts="${1%%.*}"
  ts="${ts%Z}Z"
  [ -n "$ts" ] && [ "$ts" != "Z" ] || { echo ""; return; }

  if date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$ts" '+%s' >/dev/null 2>&1; then
    date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$ts" '+%s'
  else
    date -u -d "$ts" '+%s' 2>/dev/null || echo ""
  fi
}

now_epoch() { date -u '+%s'; }

# humanize_remaining <expires-epoch> — "3h12m", or "expired" when in the past.
humanize_remaining() {
  local expires="$1" now delta
  now="$(now_epoch)"
  delta=$(( expires - now ))

  if [ "$delta" -le 0 ]; then
    echo "expired"
  elif [ "$delta" -lt 3600 ]; then
    echo "$(( delta / 60 ))m"
  else
    echo "$(( delta / 3600 ))h$(( (delta % 3600) / 60 ))m"
  fi
}

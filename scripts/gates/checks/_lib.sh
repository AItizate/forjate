#!/usr/bin/env bash
# Shared helpers for gate check scripts. Source it; do not run it.
#
# Contract (set by scripts/gates/gates.py):
#   UC_NAME, UC_DIR, UC_NS, STAGE (the stage being unlocked), STAGE_DIR (its overlay),
#   SOURCE_STAGE, TRANSITION, GATE_ID, GATE_TEXT, REPO, CHECKS_DIR.
# Exit codes: 0 pass, 1 fail, 2 skipped (print the reason on the last line).
set -uo pipefail
: "${UC_NAME:?}" "${UC_DIR:?}" "${STAGE:?}" "${STAGE_DIR:?}" "${REPO:?}"
UC_NS="${UC_NS:-uc-${UC_NAME}}"
BUILDER_DIR="${UC_DIR}/.builder"
PY="${REPO}/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

pass() { echo "PASS: $*"; exit 0; }
fail() { echo "FAIL: $*"; exit 1; }
skip() { echo "SKIPPED: $*"; exit 2; }

# kustomize_build <dir> → manifest on stdout (standalone kustomize or kubectl's copy)
kustomize_build() {
  if command -v kustomize >/dev/null 2>&1; then kustomize build --enable-helm "$1"; else kubectl kustomize --enable-helm "$1"; fi
}

# built_stage → path of a temp file with the built STAGE_DIR manifest (fails when it does not build)
built_stage() {
  [ -d "$STAGE_DIR" ] || fail "stage overlay ${STAGE_DIR#"$REPO"/} does not exist; assemble the stage first"
  local out; out="$(mktemp -t gate-XXXXXX)"
  if ! kustomize_build "$STAGE_DIR" > "$out" 2> "${out}.err"; then
    cat "${out}.err" >&2; fail "kustomize build ${STAGE_DIR#"$REPO"/} failed"
  fi
  echo "$out"
}

# record_setting <area> <stage> <key> → value or "" (reads .builder/decisions/<area>.yaml)
record_setting() {
  local f="${BUILDER_DIR}/decisions/$1.yaml"
  [ -f "$f" ] || { echo ""; return; }
  yq -r ".spec.stages.$2.settings.$3 // \"\"" "$f" 2>/dev/null
}

# record_list <area> <stage> <key> → one item per line
record_list() {
  local f="${BUILDER_DIR}/decisions/$1.yaml"
  [ -f "$f" ] || return 0
  yq -r "(.spec.stages.$2.settings.$3 // [])[]" "$f" 2>/dev/null
}

# live_kubeconfig → path when the use case namespace exists on the ephemeral cluster, else ""
live_kubeconfig() {
  local kc="${KUBECONFIG_UC:-$HOME/.kube/${UC_SHARED_CLUSTER:-forjate-uc-shared}.yaml}"
  [ -f "$kc" ] || { echo ""; return; }
  if kubectl --kubeconfig "$kc" get ns "$UC_NS" >/dev/null 2>&1; then echo "$kc"; else echo ""; fi
}

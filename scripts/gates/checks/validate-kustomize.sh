#!/usr/bin/env bash
# The stage overlay builds and passes kubeconform.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
command -v kubeconform >/dev/null || skip "kubeconform not installed"
kubeconform -strict -ignore-missing-schemas -summary "$m" || fail "kubeconform failed on ${STAGE_DIR#"$REPO"/}"
pass "${STAGE_DIR#"$REPO"/} builds and passes kubeconform"

#!/usr/bin/env bash
# The use case namespace carries the PSA enforce label the security record demands for the stage.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
want="$(record_setting security "$STAGE" psa_level)"
have="$(yq ea -r "[select(.kind == \"Namespace\" and .metadata.name == \"$UC_NS\")] | .[0].metadata.labels[\"pod-security.kubernetes.io/enforce\"] // \"\"" "$m")"
[ -n "$have" ] || fail "Namespace $UC_NS has no pod-security.kubernetes.io/enforce label"
if [ -n "$want" ] && [ "$want" != "$have" ]; then fail "enforce label is '$have', security record says '$want' at $STAGE"; fi
pass "PSA enforce=$have on $UC_NS"

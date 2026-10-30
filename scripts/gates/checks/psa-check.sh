#!/usr/bin/env bash
# The use case namespace carries the PSA enforce label the security record demands for the stage, and every
# PSA exception namespace the build labels carries the level the record's psa_exceptions give it.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
want="$(record_setting security "$STAGE" psa_level)"
label() { yq ea -r "[select(.kind == \"Namespace\" and .metadata.name == \"$1\")] | .[0].metadata.labels[\"pod-security.kubernetes.io/enforce\"] // \"\"" "$m"; }
have="$(label "$UC_NS")"
[ -n "$have" ] || fail "Namespace $UC_NS has no pod-security.kubernetes.io/enforce label"
if [ -n "$want" ] && [ "$want" != "$have" ]; then fail "enforce label is '$have', security record says '$want' at $STAGE"; fi
checked=0
while read -r ns level; do
  [ -n "$ns" ] || continue
  [ "$ns" != "$UC_NS" ] || fail "psa_exceptions names $UC_NS: an exception never lowers the use case's namespace"
  got="$(label "$ns")"
  [ -n "$got" ] || continue   # not declared or not labelled by this build: the cluster's or its owner's namespace
  [ "$got" = "$level" ] || fail "Namespace $ns enforces '$got', the security record's exception says '$level' at $STAGE"
  checked=$((checked + 1))
done < <(yq -r ".spec.stages.$STAGE.psa_exceptions[]? | .namespace + \" \" + .level" "${BUILDER_DIR}/decisions/security.yaml" 2>/dev/null)
pass "PSA enforce=$have on $UC_NS; $checked exception namespace(s) at their recorded level"

#!/usr/bin/env bash
# When the security record requires a per-workload egress matrix, each architecture workload has its own NetworkPolicy.
source "$(dirname "$0")/_lib.sh"
want="$(record_setting security "$STAGE" egress_matrix)"
[ "$want" = "required" ] || skip "egress_matrix is '${want:-none}' at $STAGE; the per-workload matrix is not required"
m="$(built_stage)" || { echo "$m"; exit 1; }
bad=0
while IFS= read -r w; do
  [ -n "$w" ] || continue
  n="$(yq ea -r "[select(.kind == \"NetworkPolicy\" and .spec.podSelector.matchLabels.app == \"$w\")] | length" "$m")"
  [ "$n" -ge 1 ] || { echo "  no NetworkPolicy selects app=$w"; bad=1; }
done < <(record_list architecture "$STAGE" workloads)
[ "$bad" -eq 0 ] || fail "workloads without a per-workload policy"
pass "every workload has its own NetworkPolicy"

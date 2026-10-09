#!/usr/bin/env bash
# The compliance record's licence inventory covers every component any record chooses for the stage.
source "$(dirname "$0")/_lib.sh"
f="${BUILDER_DIR}/decisions/compliance.yaml"; [ -f "$f" ] || skip "no compliance record"
inv="$(record_list compliance "$STAGE" licences)"
missing=0; n=0
while IFS= read -r c; do
  [ -n "$c" ] || continue; n=$((n+1))
  echo "$inv" | grep -q "$c" || { echo "  $c not in the licence inventory at $STAGE"; missing=1; }
done < <(for r in "$BUILDER_DIR"/decisions/*.yaml; do yq -r "(.spec.stages.$STAGE.choice // [])[]" "$r"; done | sort -u)
[ "$missing" -eq 0 ] || fail "components missing from the licence inventory"
pass "$n component(s) at $STAGE all in the licence inventory"

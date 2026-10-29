#!/usr/bin/env bash
# Images of the use case's own workloads follow the security record's image_policy for the stage.
source "$(dirname "$0")/_lib.sh"
want="$(record_setting security "$STAGE" image_policy)"
[ "$want" = "any" ] || [ -z "$want" ] && pass "image_policy is any at $STAGE"
m="$(built_stage)" || { echo "$m"; exit 1; }
bad=0; n=0
while IFS= read -r img; do
  [ -n "$img" ] || continue; n=$((n+1))
  case "$want" in
    pinned-digest|signed) [[ "$img" == *@sha256:* ]] || { echo "  $img is not pinned by digest"; bad=1; } ;;
  esac
done < <(yq ea -r "select((.metadata.labels[\"forjate.io/usecase\"] // \"\") == \"$UC_NAME\") | .. | select(has(\"image\")) | .image" "$m" 2>/dev/null | sort -u)
[ "$n" -ge 1 ] || fail "no workload labelled forjate.io/usecase=$UC_NAME in the built stage"
[ "$bad" -eq 0 ] || fail "images not pinned by digest ($want)"
[ "$want" = "signed" ] && echo "  signature verification is the CI step the devops record names (cosign); not checked here"
pass "$n image(s) pinned by digest"

#!/usr/bin/env bash
# A LiteLLM config in the use case only routes to in-cluster endpoints and holds no provider key.
source "$(dirname "$0")/_lib.sh"
cfgs="$(find "$UC_DIR" -path '*/configs/*' -name '*litellm*' 2>/dev/null || true)"
[ -n "$cfgs" ] || skip "no LiteLLM config under ${UC_DIR#"$REPO"/}/**/configs/; no gateway to check"
bad=0
for f in $cfgs; do
  while IFS= read -r base; do
    [ -n "$base" ] || continue
    host="$(echo "$base" | sed -E 's#^[a-z]+://##; s#[:/].*##')"
    [[ "$host" == *.svc.cluster.local || "$host" != *.* ]] || { echo "  $f: api_base $base leaves the cluster"; bad=1; }
  done < <(yq -r '(.model_list // [])[] | .litellm_params.api_base // ""' "$f" 2>/dev/null)
  grep -nE 'api_key:\s*"?sk-' "$f" && { echo "  $f: provider key literal"; bad=1; }
done
[ "$bad" -eq 0 ] || fail "LiteLLM config routes outside the cluster or carries a key"
pass "LiteLLM routes only to in-cluster endpoints, no provider key literal"

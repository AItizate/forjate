#!/usr/bin/env bash
# Every Ingress of the use case namespace sits behind the auth the security record names.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
want="$(record_setting security "$STAGE" auth_in_front)"
[ -n "$want" ] || want="$(record_setting architecture "$STAGE" auth_in_front)"
case "$want" in
  none|"") pass "auth_in_front is none at $STAGE; nothing to check" ;;
  api-key) pass "auth_in_front is api-key at $STAGE: verified by the app's webhook test, not by an Ingress annotation" ;;
esac
bad=0; n=0
while IFS=$'\t' read -r name ann; do
  [ -n "$name" ] || continue
  echo "$name" | grep -qiE 'gotrue|oauth2' && continue   # the identity provider's own Ingress cannot sit behind itself
  n=$((n+1))
  echo "$ann" | grep -qiE 'gotrue|oauth2' || { echo "  Ingress $name has no auth middleware (annotation: '${ann:-none}')"; bad=1; }
done < <(yq ea -r "[select(.kind == \"Ingress\" and (.metadata.namespace // \"$UC_NS\") == \"$UC_NS\")] | .[] | .metadata.name + \"\t\" + (.metadata.annotations[\"traefik.ingress.kubernetes.io/router.middlewares\"] // \"\")" "$m")
[ "$n" -ge 1 ] || fail "auth_in_front is $want but no Ingress is rendered in $UC_NS"
[ "$bad" -eq 0 ] || fail "an exposed surface is not behind $want"
pass "$n Ingress(es) in $UC_NS behind the auth middleware chain"

#!/usr/bin/env bash
# default-deny NetworkPolicy (ingress+egress) and allow-dns exist in the stage overlay for the use case namespace.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
have_deny="$(yq ea -r "[select(.kind == \"NetworkPolicy\" and .metadata.name == \"default-deny\" and (.metadata.namespace // \"$UC_NS\") == \"$UC_NS\")] | length" "$m")"
[ "$have_deny" -ge 1 ] || fail "no NetworkPolicy named default-deny in namespace $UC_NS"
types="$(yq ea -r "[select(.kind == \"NetworkPolicy\" and .metadata.name == \"default-deny\")] | .[0].spec.policyTypes | join(\",\")" "$m")"
[[ "$types" == *Ingress* && "$types" == *Egress* ]] || fail "default-deny policyTypes is '$types', expected Ingress and Egress"
have_dns="$(yq ea -r "[select(.kind == \"NetworkPolicy\" and .metadata.name == \"allow-dns\")] | length" "$m")"
[ "$have_dns" -ge 1 ] || fail "no allow-dns NetworkPolicy next to default-deny (DNS would be blocked)"
# every external destination in the security record's egress_allowlist has a policy naming its host
missing=0
while IFS= read -r dest; do
  [ -n "$dest" ] || continue
  host="${dest%%:*}"; host="${host%% *}"
  if ! grep -q "$host" "$m"; then echo "  no policy mentions $host"; missing=1; fi
done < <(record_list security "$STAGE" egress_allowlist | sed 's/#.*//')
[ "$missing" -eq 0 ] || fail "egress allow-list destinations without a policy"
pass "default-deny + allow-dns in $UC_NS, allow-list destinations covered"

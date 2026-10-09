#!/usr/bin/env bash
# The stage overlay uses the secrets mechanism the security record demands and ships no plain Secret.
source "$(dirname "$0")/_lib.sh"
m="$(built_stage)" || { echo "$m"; exit 1; }
want="$(record_setting security "$STAGE" secrets_mechanism)"
plain="$(yq ea -r "[select(.kind == \"Secret\" and (.metadata.namespace // \"$UC_NS\") == \"$UC_NS\" and ((.data // {}) | length > 0 or (.stringData // {}) | length > 0))] | length" "$m")"
case "$want" in
  sealed-secrets)
    n="$(yq ea -r '[select(.kind == "SealedSecret")] | length' "$m")"
    [ "$n" -ge 1 ] || fail "secrets_mechanism is sealed-secrets but no SealedSecret in the built stage"
    [ "$plain" -eq 0 ] || fail "$plain plain Secret(s) still rendered in $UC_NS (delete the placeholder with \$patch: delete)"
    pass "$n SealedSecret(s), no plain Secret in $UC_NS" ;;
  external-secrets|vault)
    n="$(yq ea -r '[select(.kind == "ExternalSecret")] | length' "$m")"
    [ "$n" -ge 1 ] || fail "secrets_mechanism is $want but no ExternalSecret in the built stage"
    [ "$plain" -eq 0 ] || fail "$plain plain Secret(s) still rendered in $UC_NS"
    pass "$n ExternalSecret(s), no plain Secret in $UC_NS" ;;
  secret-generator|"") pass "secret-generator at $STAGE: generated Secrets are expected ($plain)" ;;
  *) fail "unknown secrets_mechanism '$want'" ;;
esac

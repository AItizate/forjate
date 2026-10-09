#!/usr/bin/env bash
# Live logs carry no payload: no IBAN/bank account, no email, no phone number in the use case's workload logs.
source "$(dirname "$0")/_lib.sh"
kc="$(live_kubeconfig)"; [ -n "$kc" ] || skip "no live environment for $UC_NAME; run ephemeral.sh up $UC_NAME and re-run"
logs="$(kubectl --kubeconfig "$kc" -n "$UC_NS" logs --all-containers --tail=2000 -l "forjate.io/usecase=$UC_NAME" 2>/dev/null || true)"
[ -n "$logs" ] || skip "no log lines with label forjate.io/usecase=$UC_NAME"
hits="$(echo "$logs" | grep -cE '\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|\+?[0-9][0-9 ().-]{8,}[0-9]' || true)"
[ "$hits" -eq 0 ] || fail "$hits log line(s) look like payload (IBAN, email or phone number)"
pass "$(echo "$logs" | wc -l | tr -d ' ') log lines, none carry IBAN, email or phone patterns"

#!/usr/bin/env bash
# Live logs carry the data class and no payload: the log-content scan plus a positive check for data_class= lines.
source "$(dirname "$0")/_lib.sh"
kc="$(live_kubeconfig)"; [ -n "$kc" ] || skip "no live environment for $UC_NAME; run ephemeral.sh up $UC_NAME and re-run"
logs="$(kubectl --kubeconfig "$kc" -n "$UC_NS" logs --all-containers --tail=2000 -l "forjate.io/usecase=$UC_NAME" 2>/dev/null || true)"
[ -n "$logs" ] || skip "no log lines with label forjate.io/usecase=$UC_NAME"
hits="$(echo "$logs" | grep -cE '\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|(\+[0-9]{1,3}[ -]?)?\(?[0-9]{2,4}\)?[ -][0-9]{3}[ -][0-9]{3,4}\b' || true)"
[ "$hits" -eq 0 ] || fail "$hits log line(s) look like payload (IBAN, email or phone number)"
dc="$(echo "$logs" | grep -c "data_class=" || true)"; [ "$dc" -ge 1 ] || fail "no log line carries data_class="
pass "$dc line(s) carry data_class=, none carry payload patterns"

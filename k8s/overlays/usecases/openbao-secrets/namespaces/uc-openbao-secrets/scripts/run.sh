#!/bin/sh
# run.sh — bootstrap.sh a second time, as the admin (the root token is gone), and
# compare everything it configures before and after. Fails on any difference, or
# if the admin's password did not survive.

set -eu
# shellcheck source=lib.sh
. /scripts/lib.sh

printf '%s' "$ADMIN_PASSWORD" > "$WORK/admin.pw"
retry 60 2 unsealed "$BAO_ADDR" || die "OpenBao is not unsealed"
retry 10 2 admin_login || die "the admin cannot log in"

# Timestamps and the identity store's modify_index record when something was
# written, not what it holds: drop them, sort keys, compare the rest.
NORMALIZE='walk(if type == "object" then with_entries(select(.key | test("(_time|_timestamp|^modify_index)$") | not)) else . end)'

dump_json() { # <title> <bao args...> — the whole response
  _title="$1"; shift
  echo "# $_title"
  as admin bao "$@" -format=json > "$WORK/r.json" || die "cannot read $_title"
  jq -S "$NORMALIZE" "$WORK/r.json"
}
dump_read() { # <path> — the data of one read
  echo "# $1"
  as admin bao read -format=json "$1" > "$WORK/r.json" || die "cannot read $1"
  jq -S ".data | $NORMALIZE" "$WORK/r.json"
}
dump_config() {
  dump_json sys/mounts secrets list
  dump_json sys/auth auth list
  dump_json sys/audit audit list
  as admin bao policy list > "$WORK/policies" || die "cannot list policies"
  grep -vx root "$WORK/policies" | while read -r p; do
    echo "# policy $p"
    as admin bao policy read "$p" || die "cannot read policy $p"
  done
  for path in \
      sys/auth/userpass/tune \
      auth/kubernetes/config \
      auth/kubernetes/role/external-secrets \
      auth/kubernetes/role/agent \
      ssh-client/config/ca \
      ssh-client/roles/agent \
      "auth/userpass/users/$ADMIN_USER" \
      "identity/entity/name/$ADMIN_USER" \
      identity/group/name/admins; do
    dump_read "$path"
  done
}

step "Configuration before"
dump_config > "$WORK/before"
echo "  $(grep -c '^# ' "$WORK/before") sections, $(wc -l < "$WORK/before") lines"

step "bootstrap.sh, second run, admin token"
if ! as admin env POLICY_DIR=/policies sh /bootstrap/bootstrap.sh "$PRINCIPALS" "$ADMIN_USER" \
       > "$WORK/bootstrap.log" 2>&1; then
  indent < "$WORK/bootstrap.log"
  die "bootstrap.sh failed"
fi
indent < "$WORK/bootstrap.log"

step "Configuration after"
dump_config > "$WORK/after"
echo "  $(grep -c '^# ' "$WORK/after") sections, $(wc -l < "$WORK/after") lines"

step "Checks"
# A dump that silently lost a section would still compare equal.
for section in "policy agent" "policy agent-onboarding" "policy external-secrets" \
               "auth/kubernetes/role/agent" "ssh-client/roles/agent" "identity/group/name/admins"; do
  check "the dump covers $section" grep -qx "# $section" "$WORK/before"
done
# die inside the policy loop only leaves its subshell: catch it here.
no_read_errors() { ! grep -q '\[ERROR\]' "$WORK/before" "$WORK/after"; }
check "every read of the dump succeeded" no_read_errors
if diff -u "$WORK/before" "$WORK/after" > "$WORK/diff"; then
  pass "configuration identical before and after the second run"
else
  fail "configuration changed on the second run:"
  indent < "$WORK/diff"
fi
check "the admin's password survived the second run" admin_login

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

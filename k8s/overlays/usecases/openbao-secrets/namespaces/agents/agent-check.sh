#!/bin/sh
# agent-check.sh — what an AI agent does with OpenBao, run from a pod in the
# agents namespace. The verify Job starts it once per login method and counts its
# [PASS]/[FAIL] lines; it exits non-zero if any check fails.
#
#   AUTH=kubernetes   logs in with the pod's ServiceAccount token (role agent)
#   AUTH=approle      logs in with role_id=$AGENT and the secret-id in /creds/secret_id
#
# Env: BAO_ADDR, AUTH, AGENT, OTHER_AGENT, EXPECTED_SHA256 (of the agent's own
# value), PRINCIPAL (an SSH principal bootstrap.sh allowed).
#
# Prints nothing secret: the agent's value is only compared by SHA-256, and the
# token and the secret-id stay in files.

set -u
umask 077
W="${HOME:-/tmp}"
PASS=0
FAIL=0
pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

# denied <command...> — true only if OpenBao refused the request with a 403.
# On success the output (which may hold a secret) is dropped, never shown.
denied() {
  _out="$("$@" 2>&1)" && return 1
  case "$_out" in
    *"Code: 403"*) return 0 ;;
  esac
  echo "      unexpected error: $(printf '%s' "$_out" | grep -v '^$' | tail -n 1)"
  return 1
}

# cert_window <openssh certificate line> — prints "valid_after valid_before".
# Walks the ssh-ed25519-cert-v01 layout (PROTOCOL.certkeys): type, nonce, public
# key, serial, cert type, key id, principals, then the two uint64 timestamps.
cert_window() {
  printf '%s' "$1" | cut -d' ' -f2 | base64 -d > "$W/cert.bin"
  od -An -v -tu1 "$W/cert.bin" | awk '
    { for (i = 1; i <= NF; i++) b[n++] = $i }
    function u32(o) { return ((b[o] * 256 + b[o + 1]) * 256 + b[o + 2]) * 256 + b[o + 3] }
    function skip(o) { return o + 4 + u32(o) }
    END {
      o = skip(0); o = skip(o); o = skip(o)   # type, nonce, public key
      o += 12                                 # serial, cert type
      o = skip(o); o = skip(o)                # key id, principals
      printf "%d %d\n", u32(o) * 4294967296 + u32(o + 4), u32(o + 8) * 4294967296 + u32(o + 12)
    }'
}

login() {
  case "$AUTH" in
    kubernetes)
      bao write -field=token auth/kubernetes/login role=agent \
        jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token ;;
    approle)
      bao write -field=token auth/approle/login role_id="$AGENT" secret_id=@/creds/secret_id ;;
    *)
      echo "unknown AUTH '$AUTH'" >&2; return 2 ;;
  esac
}

echo "agent $AGENT ($AUTH) -> $BAO_ADDR"

# A new pod can be refused for a few seconds by the NetworkPolicy controller (k3s).
n=0
until login > "$W/token" 2> "$W/login.err"; do
  n=$((n + 1))
  if [ "$n" -ge 20 ]; then
    fail "logs in with $AUTH: $(grep -v '^$' "$W/login.err" | tail -n 1)"
    exit 1
  fi
  sleep 2
done
BAO_TOKEN="$(cat "$W/token")"
export BAO_TOKEN
pass "logs in with $AUTH"

# Scoped secrets
value="$(bao kv get -mount=kv -field=value "agents/$AGENT/creds" 2> /dev/null)"
if [ -n "$value" ] && [ "$(printf '%s' "$value" | sha256sum | cut -d' ' -f1)" = "$EXPECTED_SHA256" ]; then
  pass "reads kv/agents/$AGENT/creds (value matches)"
else
  fail "reads kv/agents/$AGENT/creds"
fi
unset value

if denied bao kv get -mount=kv "agents/$OTHER_AGENT/creds"; then
  pass "403 on another agent's path (kv/agents/$OTHER_AGENT/creds)"
else
  fail "403 on another agent's path (kv/agents/$OTHER_AGENT/creds)"
fi
if denied bao kv get -mount=kv workloads/demo; then
  pass "403 on kv/workloads/demo"
else
  fail "403 on kv/workloads/demo"
fi

# Short-lived SSH certificates
cert="$(bao write -field=signed_key ssh-client/sign/agent \
          public_key=@/check/test-agent.pub valid_principals="$PRINCIPAL" 2> /dev/null)"
if [ -n "$cert" ]; then
  cert_window "$cert" > "$W/window"
  read -r after before < "$W/window"
  now="$(date +%s)"
  window=$((before - after))
  left=$((before - now))
  if [ "$window" -gt 0 ] && [ "$window" -le 3600 ] && [ "$left" -gt 0 ] && [ "$left" -le 3600 ]; then
    pass "SSH certificate for $PRINCIPAL: valid ${window}s (<= 1h), expires in ${left}s"
  else
    fail "SSH certificate for $PRINCIPAL: valid ${window}s, expires in ${left}s (want <= 3600)"
  fi
else
  fail "SSH certificate for $PRINCIPAL signed"
fi

if out="$(bao write -field=signed_key ssh-client/sign/agent \
            public_key=@/check/test-agent.pub valid_principals="$PRINCIPAL" ttl=24h 2>&1)"; then
  fail "ttl=24h refused (a certificate was issued)"
else
  case "$out" in
    *"ttl is larger than maximum allowed"*) pass "ttl=24h refused (larger than the 1h maximum)" ;;
    *) fail "ttl=24h refused for the right reason: $(printf '%s' "$out" | grep -v '^$' | tail -n 1)" ;;
  esac
fi

if out="$(bao write -field=signed_key ssh-client/sign/agent \
            public_key=@/check/test-agent.pub valid_principals=root 2>&1)"; then
  fail "principal root refused (a certificate was issued)"
else
  case "$out" in
    *"not a valid value for valid_principals"*) pass "principal root refused" ;;
    *) fail "principal root refused for the right reason: $(printf '%s' "$out" | grep -v '^$' | tail -n 1)" ;;
  esac
fi

bao token revoke -self > /dev/null 2>&1 || true
echo "agent $AGENT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

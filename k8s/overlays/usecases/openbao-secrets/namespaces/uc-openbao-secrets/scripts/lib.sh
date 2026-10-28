# shellcheck shell=sh
# lib.sh — helpers shared by the openbao-secrets lifecycle Jobs. Sourced, not run.
#
# The Job logs end up in public CI logs, so no secret may reach stdout, stderr or
# a command line: tokens and passwords live in files under $WORK (umask 077) and
# reach bao through BAO_TOKEN or stdin. A token is stored as $WORK/<name>.token
# and used with `as <name> bao ...`.
#
# Env (set by the Jobs): BAO_ADDR (Service openbao, ready pods only),
# BAO_HEADLESS (openbao-0 directly, also while uninitialised or sealed),
# ADMIN_USER, NS (this namespace), OPENBAO_NAMESPACE (where OpenBao runs).

WORK="${WORK:-/work}"
umask 077

PASS=0
FAIL=0
pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
die()  { echo "  [ERROR] $*"; exit 1; }
step() { echo ""; echo "== $*"; }

# check <description> <command...> — PASS when the command succeeds. Its output is dropped.
check() {
  _d="$1"; shift
  if "$@" > /dev/null 2>&1; then pass "$_d"; else fail "$_d"; fi
}

# retry <attempts> <interval> <command...>
retry() {
  _n="$1"; _s="$2"; shift 2
  _i=0
  until "$@"; do
    _i=$((_i + 1))
    [ "$_i" -ge "$_n" ] && return 1
    sleep "$_s"
  done
}

# as <token-name> bao ... — run bao with the token in $WORK/<token-name>.token
as() {
  _t="$1"; shift
  BAO_TOKEN="$(cat "$WORK/$_t.token")" "$@"
}

# denied <command...> — true only if OpenBao refused the request with a 403.
# On success the output (which may hold a secret) is dropped, never shown.
denied() {
  _out="$("$@" 2>&1)" && return 1
  case "$_out" in
    *"Code: 403"*) return 0 ;;
  esac
  return 1
}

# reachable <addr> — the server answers, sealed or not. `bao status` exits 1 only
# when it cannot talk to the server: a fresh pod can be refused for a few seconds
# by the NetworkPolicy controller (k3s), and a new pod needs its DNS record.
reachable() {
  _rc=0
  BAO_ADDR="$1" bao status > /dev/null 2>&1 || _rc=$?
  [ "$_rc" -ne 1 ]
}

unsealed()    { BAO_ADDR="$1" bao status > /dev/null 2>&1; }
initialized() { BAO_ADDR="$1" bao status -format=json 2> /dev/null | jq -r .initialized; }

# init_openbao <addr> <token-name> — bao operator init, keeping only the root token.
# The recovery key is discarded: an ephemeral environment never regenerates root.
init_openbao() {
  BAO_ADDR="$1" bao operator init -recovery-shares=1 -recovery-threshold=1 -format=json > "$WORK/init.json"
  jq -j .root_token "$WORK/init.json" > "$WORK/$2.token"
  rm -f "$WORK/init.json"
  [ -s "$WORK/$2.token" ]
}

# admin_login — userpass login as $ADMIN_USER with the password in $WORK/admin.pw
admin_login() {
  printf '{"password":"%s"}' "$(cat "$WORK/admin.pw")" \
    | bao write -field=token "auth/userpass/login/$ADMIN_USER" - > "$WORK/admin.token" 2> /dev/null
  [ -s "$WORK/admin.token" ]
}

# new_token <parent> <name> <policy> — a 10-minute child token with one policy
new_token() {
  as "$1" bao token create -policy="$3" -ttl=10m -field=token | tr -d '\n' > "$WORK/$2.token"
  [ -s "$WORK/$2.token" ]
}

rand_hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }
sha()      { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }

# secret_to_file <namespace> <secret> <key> <file>
secret_to_file() {
  kubectl -n "$1" get secret "$2" -o jsonpath="{.data.$3}" | base64 -d > "$4"
  [ -s "$4" ]
}

# wait_pod <namespace> <pod> <seconds> — prints Succeeded, Failed or Timeout
wait_pod() {
  _i=0
  while [ "$_i" -lt "$3" ]; do
    _p="$(kubectl -n "$1" get pod "$2" -o jsonpath='{.status.phase}' 2> /dev/null || true)"
    case "$_p" in Succeeded|Failed) echo "$_p"; return 0 ;; esac
    sleep 2; _i=$((_i + 2))
  done
  echo Timeout
}

# wait_job <namespace> <job> <seconds> — prints Complete, Failed or Timeout
wait_job() {
  _i=0
  while [ "$_i" -lt "$3" ]; do
    _c="$(kubectl -n "$1" get job "$2" -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}' 2> /dev/null || true)"
    case "$_c" in
      *"Complete=True"*) echo Complete; return 0 ;;
      *"Failed=True"*)   echo Failed;   return 0 ;;
    esac
    sleep 2; _i=$((_i + 2))
  done
  echo Timeout
}

indent() { sed 's/^/    /'; }

#!/bin/sh
# bootstrap.sh — configure a freshly initialised OpenBao (security/openbao).
#
# The component deploys the server; configuring it needs an admin token, so it
# cannot be a manifest. Run once by a human after `bao operator init`. Idempotent:
# every step checks before it creates, so running it again changes nothing.
#
#   1. kv-v2 at kv/
#   2. kubernetes auth + roles "external-secrets" (bound to ESO's ServiceAccount) and
#      "agent" (any ServiceAccount of the agents namespace); approle auth for agents
#      outside the cluster
#   3. ssh at ssh-client/, signing CA, role "agent" (TTL 30m, max 1h)
#   4. checks that an audit device is enabled (declared in openbao.hcl, not creatable by API)
#   5. every policy under k8s/components/apps/security/openbao/policies/
#   6. human administrators: userpass auth, one identity per admin, group "admins"
#      (policy admin). With this in place the root token can be revoked
#
# Usage:
#   BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=<admin or root token> \
#     scripts/openbao/bootstrap.sh <principal>[,<principal>...] <admin>[,<admin>...]
#
#   <principal>   unix users the SSH CA may put in a certificate (role "agent")
#   <admin>       human administrators. Each gets an identity and a userpass account that
#                 NOBODY can log in to yet: the script sets a random password it never
#                 shows. An operator then sets the person's own password (see
#                 docs/tenant-onboarding/openbao-admins.md). Existing accounts and their
#                 passwords are never touched, and the group only ever gains members.
#                 Names: letters, digits . _ -
#
# Works with the root token and, once an admin exists, with that admin's token.
#
# Environment:
#   BAO_ADDR, BAO_TOKEN   required (the token is never printed)
#   ESO_SA_NAME           ServiceAccount of External Secrets   (default external-secrets)
#   ESO_SA_NAMESPACE      its namespace                        (default external-secrets)
#   AGENT_NAMESPACE       namespace whose ServiceAccounts are agents (default agents)
#   K8S_HOST              API server as seen from OpenBao      (default https://kubernetes.default.svc:443)
#   POLICY_DIR            policy files                         (default: next to the component)
#
# Needs the `bao` CLI (POSIX sh only, so it also runs inside the openbao image).
# Prints no secret. The SSH CA public key, which hosts need in TrustedUserCAKeys,
# is printed at the end.

set -eu

if [ $# -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
fi
PRINCIPALS="$1"
ADMINS="$2"
: "${BAO_ADDR:?BAO_ADDR is required}"
: "${BAO_TOKEN:?BAO_TOKEN is required}"
export BAO_ADDR BAO_TOKEN

ESO_SA_NAME="${ESO_SA_NAME:-external-secrets}"
ESO_SA_NAMESPACE="${ESO_SA_NAMESPACE:-external-secrets}"
AGENT_NAMESPACE="${AGENT_NAMESPACE:-agents}"
K8S_HOST="${K8S_HOST:-https://kubernetes.default.svc:443}"
HERE="$(cd "$(dirname "$0")" && pwd)"
POLICY_DIR="${POLICY_DIR:-$HERE/../../k8s/components/apps/security/openbao/policies}"
DEFAULT_USER="${PRINCIPALS%%,*}"

say() { printf '%s\n' "$*"; }

command -v bao > /dev/null || { say "bao CLI not found" >&2; exit 1; }
[ -d "$POLICY_DIR" ] || { say "policy dir not found: $POLICY_DIR" >&2; exit 1; }

# Fail early and legibly if the server is unreachable, sealed or the token is wrong.
bao token lookup > /dev/null || { say "cannot authenticate to $BAO_ADDR" >&2; exit 1; }

has_mount() { bao secrets list -format=json | grep -q "\"$1/\""; }
has_auth()  { bao auth list -format=json | grep -q "\"$1/\""; }
has_audit() { bao audit list -format=json | grep -q "\"$1/\""; }

# 1. kv-v2
if has_mount kv; then
  say "kv: present"
else
  bao secrets enable -path=kv -version=2 kv > /dev/null
  say "kv: enabled (kv-v2)"
fi

# 2. kubernetes auth. Re-writing config and role with identical values is a no-op.
if has_auth kubernetes; then
  say "auth/kubernetes: present"
else
  bao auth enable kubernetes > /dev/null
  say "auth/kubernetes: enabled"
fi
bao write auth/kubernetes/config kubernetes_host="$K8S_HOST" > /dev/null
bao write auth/kubernetes/role/external-secrets \
  bound_service_account_names="$ESO_SA_NAME" \
  bound_service_account_namespaces="$ESO_SA_NAMESPACE" \
  policies=external-secrets \
  ttl=1h > /dev/null
say "auth/kubernetes: role external-secrets -> $ESO_SA_NAMESPACE/$ESO_SA_NAME"

# Agents inside the cluster: no per-agent setup. Any ServiceAccount of the agents
# namespace may log in, and its name becomes the identity alias (and the kv path).
# Whoever can create ServiceAccounts there can mint agents: guard that namespace.
bao write auth/kubernetes/role/agent \
  bound_service_account_names='*' \
  bound_service_account_namespaces="$AGENT_NAMESPACE" \
  alias_name_source=serviceaccount_name \
  policies=agent \
  ttl=30m \
  max_ttl=1h > /dev/null
say "auth/kubernetes: role agent -> any ServiceAccount in $AGENT_NAMESPACE"

# Agents outside the cluster: one AppRole per agent, created by agent-onboarding.
if has_auth approle; then
  say "auth/approle: present"
else
  bao auth enable approle > /dev/null
  say "auth/approle: enabled"
fi

# 3. SSH CA. Generating a second key would replace the CA every host trusts, so
# only generate when none exists.
if has_mount ssh-client; then
  say "ssh-client: present"
else
  bao secrets enable -path=ssh-client ssh > /dev/null
  say "ssh-client: enabled"
fi
if bao read -field=public_key ssh-client/config/ca > /dev/null 2>&1; then
  say "ssh-client: CA present"
else
  bao write ssh-client/config/ca generate_signing_key=true key_type=ed25519 > /dev/null
  say "ssh-client: CA generated (ed25519)"
fi
# JSON on stdin: default_extensions is a map, which key=value arguments cannot carry.
case "$PRINCIPALS" in
  *[!A-Za-z0-9._,-]*) say "principals may only contain letters, digits . _ - and commas" >&2; exit 2 ;;
esac
bao write ssh-client/roles/agent - > /dev/null <<JSON
{
  "key_type": "ca",
  "algorithm_signer": "default",
  "allow_user_certificates": true,
  "allowed_users": "$PRINCIPALS",
  "default_user": "$DEFAULT_USER",
  "default_extensions": { "permit-pty": "" },
  "ttl": "30m",
  "max_ttl": "1h"
}
JSON
say "ssh-client: role agent (principals: $PRINCIPALS, ttl 30m, max 1h)"

# 4. audit. OpenBao refuses to create audit devices through the API: the component
# declares one in openbao.hcl. Here we only check one is enabled, and say so loudly
# at the end if not, after everything else is configured.
AUDIT_MISSING=0
if [ "$(bao audit list -format=json | grep -c '"type"')" -gt 0 ]; then
  say "audit: enabled ($(bao audit list -format=json | grep -o '"[^"]*/": {' | tr -d '":{ ' | tr '\n' ' '))"
else
  AUDIT_MISSING=1
  say "audit: NO AUDIT DEVICE (declare one in openbao.hcl and restart the pod)" >&2
fi

# 5. policies. Templates may carry __ACCESSOR_<METHOD>__ placeholders: the identity
# templates in policies need the mount accessor, which only exists after step 2.
ACC_KUBERNETES="$(bao read -field=accessor sys/auth/kubernetes)"
ACC_APPROLE="$(bao read -field=accessor sys/auth/approle)"
for f in "$POLICY_DIR"/*.hcl; do
  name="$(basename "$f" .hcl)"
  sed -e "s/__ACCESSOR_KUBERNETES__/$ACC_KUBERNETES/g" \
      -e "s/__ACCESSOR_APPROLE__/$ACC_APPROLE/g" "$f" | bao policy write "$name" - > /dev/null
  say "policy: $name"
done

# 6. Human administrators. The group is what carries the admin policy, so the login
# method can change later (OIDC) without touching policies: only the alias differs.
case "$ADMINS" in
  *[!A-Za-z0-9._,-]*) say "admin names may only contain letters, digits . _ - and commas" >&2; exit 2 ;;
esac
if has_auth userpass; then
  say "auth/userpass: present"
else
  bao auth enable userpass > /dev/null
  say "auth/userpass: enabled"
fi
# Admin tokens are short-lived: the default (32 days) is far too long for this policy.
bao auth tune -default-lease-ttl=8h -max-lease-ttl=24h userpass/ > /dev/null
say "auth/userpass: token TTL 8h, max 24h"
ACC_USERPASS="$(bao read -field=accessor sys/auth/userpass)"

# Current members, so the group only ever gains people. Removing one is deliberate.
MEMBERS="$(bao read -field=member_entity_ids identity/group/name/admins 2> /dev/null | tr -d '[]' | tr ' ' ',')"
[ "$MEMBERS" != "<nil>" ] || MEMBERS=""

for h in $(printf '%s' "$ADMINS" | tr ',' ' '); do
  if ID="$(bao read -field=id "identity/entity/name/$h" 2> /dev/null)"; then
    say "admin $h: identity present"
  else
    ID="$(bao write -field=id "identity/entity" name="$h")"
    say "admin $h: identity created"
  fi
  if bao read -format=json "identity/entity/name/$h" | grep -q "\"mount_accessor\": \"$ACC_USERPASS\""; then
    say "admin $h: userpass alias present"
  else
    bao write identity/entity-alias name="$h" canonical_id="$ID" mount_accessor="$ACC_USERPASS" > /dev/null
    say "admin $h: userpass alias created"
  fi
  if bao read "auth/userpass/users/$h" > /dev/null 2>&1; then
    say "admin $h: userpass account present (password untouched)"
  else
    # Nobody knows this password: the account is unusable until an operator sets one.
    pw="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    printf '{"password":"%s"}' "$pw" | bao write "auth/userpass/users/$h" - > /dev/null
    say "admin $h: userpass account created, NO usable password yet"
  fi
  case ",$MEMBERS," in
    *",$ID,"*) ;;
    *) MEMBERS="${MEMBERS:+$MEMBERS,}$ID" ;;
  esac
done
bao write identity/group/name/admins type=internal policies=admin member_entity_ids="$MEMBERS" > /dev/null
say "group admins: policy admin, members: $(printf '%s' "$MEMBERS" | tr ',' '\n' | grep -c .)"

say ""
say "SSH CA public key (TrustedUserCAKeys on every host the agent logs in to):"
bao read -field=public_key ssh-client/config/ca
[ "$AUDIT_MISSING" -eq 0 ] || exit 1

#!/bin/sh
# seed.sh — bring OpenBao to where a tenant leaves it after day one:
#   1. seal key for seal-static: 32 random bytes in Secret security/openbao-seal-key
#   2. bao operator init: root token kept in a file, recovery key discarded
#   3. bootstrap.sh with the root token, admin $ADMIN_USER
#   4. the admin's password (Secret openbao-admin), the snapshot token
#      (Secret security/openbao-snapshot-token), then the root token is revoked
#   5. as the admin: kv/workloads/demo. As agent-onboarding: AppRole
#      agent-$APPROLE_AGENT and kv/agents/<agent>/creds for both agents
#
# Re-runnable: on an initialised instance it logs in as the admin and only
# refreshes the fixtures. If it dies between init and Secret openbao-admin, the
# instance is lost: `ephemeral.sh down openbao-secrets` and up again.

set -eu
# shellcheck source=lib.sh
. /scripts/lib.sh

step "Seal key"
if kubectl -n security get secret openbao-seal-key > /dev/null 2>&1; then
  echo "  Secret security/openbao-seal-key present"
else
  head -c 32 /dev/urandom > "$WORK/seal.key"
  kubectl -n security create secret generic openbao-seal-key \
    --from-file=current.key="$WORK/seal.key" > /dev/null
  rm -f "$WORK/seal.key"
  echo "  Secret security/openbao-seal-key created (32 random bytes)"
  # openbao-0 has been waiting for the Secret: recreate it instead of waiting out
  # the kubelet's mount backoff.
  kubectl -n security delete pod openbao-0 --ignore-not-found --wait=false > /dev/null
fi

step "OpenBao"
retry 150 2 reachable "$BAO_HEADLESS" || die "openbao-0 did not answer within 5 minutes"

if [ "$(initialized "$BAO_HEADLESS")" = "true" ]; then
  echo "  already initialised: continuing as $ADMIN_USER (Secret openbao-admin)"
  kubectl -n "$NS" get secret openbao-admin > /dev/null 2>&1 \
    || die "initialised, but Secret openbao-admin is missing: run 'ephemeral.sh down openbao-secrets' and up again"
  secret_to_file "$NS" openbao-admin password "$WORK/admin.pw" || die "cannot read Secret openbao-admin"
  retry 60 2 unsealed "$BAO_ADDR" || die "OpenBao is not unsealed"
  retry 10 2 admin_login || die "the admin cannot log in"
else
  init_openbao "$BAO_HEADLESS" root || die "bao operator init failed"
  echo "  initialised (recovery key discarded; the root token never leaves this pod)"
  retry 60 2 unsealed "$BAO_ADDR" || die "OpenBao did not unseal itself with the static key"
  echo "  unsealed by the static key and ready behind $BAO_ADDR"

  step "bootstrap.sh, first run, root token"
  if ! as root env POLICY_DIR=/policies sh /bootstrap/bootstrap.sh "$PRINCIPALS" "$ADMIN_USER" \
         > "$WORK/bootstrap.log" 2>&1; then
    indent < "$WORK/bootstrap.log"
    die "bootstrap.sh failed"
  fi
  indent < "$WORK/bootstrap.log"

  step "Admin $ADMIN_USER"
  rand_hex 24 > "$WORK/admin.pw"
  # Stored before it is set: losing a password OpenBao already holds would
  # strand the environment with the root token revoked.
  kubectl -n "$NS" create secret generic openbao-admin \
    --from-literal=username="$ADMIN_USER" --from-file=password="$WORK/admin.pw" \
    --dry-run=client -o yaml | kubectl apply -f - > /dev/null
  printf '{"password":"%s"}' "$(cat "$WORK/admin.pw")" \
    | as root bao write "auth/userpass/users/$ADMIN_USER/password" - > /dev/null
  retry 5 2 admin_login || die "the admin cannot log in with the password just set"
  echo "  password set and stored in Secret openbao-admin; login works"

  step "Snapshot token"
  as root bao token create -policy=raft-snapshot -orphan -period=720h -field=token \
    | tr -d '\n' > "$WORK/snapshot.token"
  [ -s "$WORK/snapshot.token" ] || die "cannot create the snapshot token"
  kubectl -n security create secret generic openbao-snapshot-token \
    --from-file=token="$WORK/snapshot.token" --dry-run=client -o yaml | kubectl apply -f - > /dev/null
  rm -f "$WORK/snapshot.token"
  echo "  periodic orphan token, policy raft-snapshot, in Secret security/openbao-snapshot-token"

  step "Root token"
  as root bao token revoke -self > /dev/null
  if as root bao token lookup > /dev/null 2>&1; then
    die "the root token still works after revoke"
  fi
  rm -f "$WORK/root.token"
  echo "  revoked; everything from here on runs as $ADMIN_USER"
fi

step "Fixtures"
if ! kubectl -n "$NS" get secret openbao-fixtures > /dev/null 2>&1; then
  for k in workload agent_k8s agent_approle; do rand_hex 16 > "$WORK/fx.$k"; done
  kubectl -n "$NS" create secret generic openbao-fixtures \
    --from-file=workload="$WORK/fx.workload" \
    --from-file=agent_k8s="$WORK/fx.agent_k8s" \
    --from-file=agent_approle="$WORK/fx.agent_approle" > /dev/null
fi
for k in workload agent_k8s agent_approle; do
  secret_to_file "$NS" openbao-fixtures "$k" "$WORK/fx.$k" || die "cannot read Secret openbao-fixtures"
done

printf '{"value":"%s"}' "$(cat "$WORK/fx.workload")" \
  | as admin bao kv put -mount=kv workloads/demo - > /dev/null
echo "  kv/workloads/demo (as $ADMIN_USER)"

# Agents are registered the way docs/tenant-onboarding/agent-secrets.md tells a
# tenant's automation to: with a token that only holds agent-onboarding.
new_token admin onboarding agent-onboarding || die "cannot create an agent-onboarding token"
as onboarding bao write "auth/approle/role/agent-$APPROLE_AGENT" \
  role_id="$APPROLE_AGENT" token_policies=agent \
  token_ttl=30m token_max_ttl=1h secret_id_ttl=1h > /dev/null
echo "  AppRole agent-$APPROLE_AGENT, role_id $APPROLE_AGENT (as agent-onboarding)"
printf '{"value":"%s"}' "$(cat "$WORK/fx.agent_k8s")" \
  | as onboarding bao kv put -mount=kv "agents/$K8S_AGENT/creds" - > /dev/null
printf '{"value":"%s"}' "$(cat "$WORK/fx.agent_approle")" \
  | as onboarding bao kv put -mount=kv "agents/$APPROLE_AGENT/creds" - > /dev/null
echo "  kv/agents/$K8S_AGENT/creds, kv/agents/$APPROLE_AGENT/creds (as agent-onboarding)"
as onboarding bao token revoke -self > /dev/null

step "External Secrets"
# The store was refused until bootstrap.sh created role external-secrets; ESO
# would retry on its own, this only saves the wait.
kubectl annotate clustersecretstore openbao force-sync="$(date +%s)" --overwrite > /dev/null
echo "  ClusterSecretStore openbao asked to re-validate"

echo ""
echo "seed done"

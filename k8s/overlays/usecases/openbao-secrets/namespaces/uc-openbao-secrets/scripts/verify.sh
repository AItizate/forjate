#!/bin/sh
# verify.sh — exits 0 only if every claim of step 6 in docs/openbao-plan.md holds:
#   1. External Secrets (v1) syncs kv/workloads/demo through ClusterSecretStore
#      openbao, and an ExternalSecret on kv/agents/... does not sync
#   2. a Kubernetes agent and an AppRole agent each read their own path, get a 403
#      on the other's and on workloads/, sign an SSH certificate valid <= 1h, and
#      are refused ttl=24h (agent-check.sh, in pods of the agents namespace)
#   3. agent-onboarding cannot create a role that carries another policy
#   4. raft snapshot -> data PVC wiped -> restore -> the data is back
# Every check runs and the summary decides. 4 is destructive, so it goes last.

set -u
# shellcheck source=lib.sh
. /scripts/lib.sh

printf '%s' "$ADMIN_PASSWORD" > "$WORK/admin.pw"
retry 60 2 unsealed "$BAO_ADDR" || die "OpenBao is not unsealed"
retry 10 2 admin_login || die "the admin cannot log in"

WORKLOAD_SHA="$(sha "$FIXTURE_WORKLOAD")"
OPENBAO_IMAGE="$(kubectl -n security get statefulset openbao -o jsonpath='{.spec.template.spec.containers[0].image}')"

# ── 1. External Secrets ──────────────────────────────────────────────────────
step "1. External Secrets"

ready_status() { kubectl -n "$NS" get "$1" "$2" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2> /dev/null; }
ready_reason() { kubectl -n "$NS" get "$1" "$2" -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}' 2> /dev/null; }
secret_sha()   { kubectl -n "$NS" get secret "$1" -o jsonpath='{.data.value}' 2> /dev/null | base64 -d | sha256sum | cut -d' ' -f1; }

store_ready()   { [ "$(ready_status clustersecretstore openbao)" = "True" ]; }
demo_synced()   { [ "$(ready_status externalsecret demo-workload)" = "True" ] && [ "$(secret_sha demo-workload)" = "$WORKLOAD_SHA" ]; }
agent_refused() {
  [ "$(ready_reason externalsecret forbidden-agent-path)" = "SecretSyncedError" ] \
    && ! kubectl -n "$NS" get secret forbidden-agent-path > /dev/null 2>&1
}

kubectl annotate clustersecretstore openbao force-sync="$(date +%s)" --overwrite > /dev/null
check "ClusterSecretStore openbao is Ready" retry 45 2 store_ready
kubectl -n "$NS" annotate externalsecret demo-workload forbidden-agent-path force-sync="$(date +%s)" --overwrite > /dev/null
check "ExternalSecret demo-workload (external-secrets.io/v1) syncs kv/workloads/demo with the right value" \
  retry 60 2 demo_synced
# Judged only after the store has proved it works, and after more than two
# refresh intervals: an error left from before bootstrap.sh would otherwise pass.
sleep 25
check "ExternalSecret on kv/agents/$K8S_AGENT/creds refused (SecretSyncedError, no Secret)" agent_refused

# ── 2. Agents ────────────────────────────────────────────────────────────────
step "2. Agents"

# agent_pod <pod> <auth> <agent> <other agent> <expected sha256> — manifest on stdout
agent_pod() {
  if [ "$2" = kubernetes ]; then
    sa="$3"; automount=true; creds_mount=""; creds_volume=""
  else
    sa=default; automount=false
    creds_mount="
        - { name: creds, mountPath: /creds, readOnly: true }"
    creds_volume="
    - name: creds
      secret: { secretName: agent-approle-creds, defaultMode: 0440 }"
  fi
  cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $1
  namespace: agents
  labels: { app: openbao-agent-check }
spec:
  restartPolicy: Never
  serviceAccountName: $sa
  automountServiceAccountToken: $automount
  securityContext:
    runAsNonRoot: true
    runAsUser: 100
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: agent
      image: $OPENBAO_IMAGE
      command: ["sh", "/check/agent-check.sh"]
      env:
        - { name: BAO_ADDR, value: "http://openbao.security.svc:8200" }
        - { name: HOME, value: /tmp }
        - { name: AUTH, value: "$2" }
        - { name: AGENT, value: "$3" }
        - { name: OTHER_AGENT, value: "$4" }
        - { name: EXPECTED_SHA256, value: "$5" }
        - { name: PRINCIPAL, value: "$PRINCIPALS" }
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: ["ALL"] }
      resources:
        requests: { cpu: 10m, memory: 32Mi }
        limits: { cpu: 200m, memory: 128Mi }
      volumeMounts:
        - { name: check, mountPath: /check, readOnly: true }
        - { name: tmp, mountPath: /tmp }$creds_mount
  volumes:
    - name: check
      configMap: { name: agent-check }
    - name: tmp
      emptyDir: {}$creds_volume
EOF
}

# run_agent <pod> <auth> <agent> <other agent> <expected value>
run_agent() {
  kubectl -n agents delete pod "$1" --ignore-not-found --wait=true > /dev/null 2>&1
  agent_pod "$1" "$2" "$3" "$4" "$(sha "$5")" | kubectl apply -f - > /dev/null
  _phase="$(wait_pod agents "$1" 240)"
  kubectl -n agents logs "$1" > "$WORK/agent.log" 2>&1 || true
  indent < "$WORK/agent.log"
  # Every check of the agent counts here too.
  PASS=$((PASS + $(grep -c '^\[PASS\]' "$WORK/agent.log")))
  FAIL=$((FAIL + $(grep -c '^\[FAIL\]' "$WORK/agent.log")))
  if [ "$_phase" = Succeeded ]; then
    pass "$2 agent $3: pod succeeded"
  else
    fail "$2 agent $3: pod $_phase"
  fi
  kubectl -n agents delete pod "$1" --ignore-not-found --wait=false > /dev/null 2>&1
}

# The AppRole agent's secret-id comes from agent-onboarding, as for a real one.
kubectl -n agents delete secret agent-approle-creds --ignore-not-found > /dev/null
if new_token admin onboarding agent-onboarding \
   && as onboarding bao write -f -field=secret_id "auth/approle/role/agent-$APPROLE_AGENT/secret-id" \
        | tr -d '\n' > "$WORK/secret_id" \
   && [ -s "$WORK/secret_id" ]; then
  kubectl -n agents create secret generic agent-approle-creds --from-file=secret_id="$WORK/secret_id" > /dev/null
  pass "agent-onboarding issued a secret-id for agent-$APPROLE_AGENT"
else
  fail "agent-onboarding issued a secret-id for agent-$APPROLE_AGENT"
fi
rm -f "$WORK/secret_id"

echo "  Kubernetes agent (ServiceAccount agents/$K8S_AGENT):"
run_agent agent-check-k8s kubernetes "$K8S_AGENT" "$APPROLE_AGENT" "$FIXTURE_AGENT_K8S"
echo "  AppRole agent (role_id $APPROLE_AGENT):"
run_agent agent-check-approle approle "$APPROLE_AGENT" "$K8S_AGENT" "$FIXTURE_AGENT_APPROLE"
kubectl -n agents delete secret agent-approle-creds --ignore-not-found > /dev/null

# ── 3. agent-onboarding limits ───────────────────────────────────────────────
step "3. agent-onboarding limits"

ROLE=auth/approle/role/agent-uc-escalate
role_absent() { as admin bao read "$ROLE" 2>&1 | grep -q '^No value found'; }

check "control: it can create a role carrying the agent policy" \
  as onboarding bao write auth/approle/role/agent-uc-probe role_id=uc-probe token_policies=agent
check "control: and delete it" as onboarding bao delete auth/approle/role/agent-uc-probe
check "403 creating a role with token_policies=admin" \
  denied as onboarding bao write "$ROLE" role_id=uc-escalate token_policies=admin
check "403 creating a role with token_policies=agent,admin" \
  denied as onboarding bao write "$ROLE" role_id=uc-escalate token_policies=agent,admin
check "403 creating a role with the legacy policies=admin" \
  denied as onboarding bao write "$ROLE" role_id=uc-escalate policies=admin
check "403 creating a role without a secret-id (bind_secret_id=false)" \
  denied as onboarding bao write "$ROLE" role_id=uc-escalate token_policies=agent bind_secret_id=false
check "no role agent-uc-escalate exists afterwards" role_absent
as onboarding bao token revoke -self > /dev/null 2>&1 || true

# ── 4. Snapshot, wipe, restore ───────────────────────────────────────────────
step "4. Snapshot -> wipe the data PVC -> restore"

MARKER=workloads/after-snapshot
marker_absent() { as admin bao kv get -mount=kv "$MARKER" 2>&1 | grep -q '^No value found'; }
demo_restored() {
  _v="$(as admin bao kv get -mount=kv -field=value workloads/demo 2> /dev/null)"
  [ -n "$_v" ] && [ "$(sha "$_v")" = "$WORKLOAD_SHA" ]
}
pvc_gone()      { ! kubectl -n security get pvc data-openbao-0 > /dev/null 2>&1; }
uninitialized() { [ "$(initialized "$BAO_HEADLESS")" = "false" ]; }

# A marker written after the snapshot must be gone after the restore. A run that
# died halfway may have left one in the instance: clear it first.
as admin bao kv metadata delete -mount=kv "$MARKER" > /dev/null 2>&1 || true

# The CronJob's own template, credentials and all: what runs every 6 hours.
SNAP_JOB="openbao-raft-snapshot-uc-$(date +%s)"
kubectl -n security create job "$SNAP_JOB" --from=cronjob/openbao-raft-snapshot > /dev/null
_st="$(wait_job security "$SNAP_JOB" 240)"
kubectl -n security logs "job/$SNAP_JOB" 2>&1 | indent
if [ "$_st" = Complete ]; then pass "snapshot saved by a Job from CronJob openbao-raft-snapshot"; else fail "snapshot Job: $_st"; fi
kubectl -n security delete job "$SNAP_JOB" --wait=false > /dev/null 2>&1

printf '{"value":"written after the snapshot"}' | as admin bao kv put -mount=kv "$MARKER" - > /dev/null

# Wipe: no pod, no PVC, then a new pod on a new, empty volume.
kubectl -n security scale statefulset openbao --replicas=0 > /dev/null
kubectl -n security wait --for=delete pod/openbao-0 --timeout=180s > /dev/null 2>&1
kubectl -n security delete pvc data-openbao-0 --wait=true --timeout=180s > /dev/null 2>&1
check "data PVC data-openbao-0 deleted" pvc_gone
kubectl -n security scale statefulset openbao --replicas=1 > /dev/null
retry 150 2 reachable "$BAO_HEADLESS" || fail "openbao-0 did not come back"
check "the new openbao-0 starts uninitialised (the data is really gone)" retry 10 2 uninitialized

# Restore as raft-snapshot/kustomization.yaml documents it: init the empty
# instance, then a throwaway pod that mounts the snapshot PVC restores with -force.
if init_openbao "$BAO_HEADLESS" fresh && retry 60 2 unsealed "$BAO_ADDR"; then
  pass "empty instance initialised and unsealed by the same static key"
else
  fail "empty instance initialised and unsealed by the same static key"
fi
kubectl -n security delete secret openbao-restore-token --ignore-not-found > /dev/null
kubectl -n security create secret generic openbao-restore-token --from-file=token="$WORK/fresh.token" > /dev/null
kubectl -n security delete pod openbao-restore --ignore-not-found --wait=true > /dev/null 2>&1
sed "s|__IMAGE__|$OPENBAO_IMAGE|" <<'EOF' | kubectl apply -f - > /dev/null
apiVersion: v1
kind: Pod
metadata:
  name: openbao-restore
  namespace: security
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 100
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: restore
      image: __IMAGE__
      command: ["sh", "-c"]
      args:
        - |
          set -eu
          n=0
          while [ "$n" -lt 30 ]; do
            rc=0; bao status > /dev/null 2>&1 || rc=$?
            [ "$rc" -ne 1 ] && break
            n=$((n + 1)); sleep 2
          done
          snap="$(ls -1t /snapshots/openbao-*.snap | head -n 1)"
          echo "restoring $snap"
          bao operator raft snapshot restore -force "$snap"
          echo "restored"
      env:
        - { name: BAO_ADDR, value: "http://openbao:8200" }
        - { name: HOME, value: /tmp }
        - name: BAO_TOKEN
          valueFrom: { secretKeyRef: { name: openbao-restore-token, key: token } }
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: ["ALL"] }
      resources:
        requests: { cpu: 10m, memory: 32Mi }
        limits: { cpu: 200m, memory: 128Mi }
      volumeMounts:
        - { name: snapshots, mountPath: /snapshots, readOnly: true }
        - { name: tmp, mountPath: /tmp }
  volumes:
    - name: snapshots
      persistentVolumeClaim: { claimName: openbao-snapshots, readOnly: true }
    - name: tmp
      emptyDir: {}
EOF
_phase="$(wait_pod security openbao-restore 240)"
kubectl -n security logs openbao-restore 2>&1 | indent
if [ "$_phase" = Succeeded ]; then pass "restore -force from the newest snapshot"; else fail "restore pod: $_phase"; fi
kubectl -n security delete pod openbao-restore --ignore-not-found --wait=false > /dev/null 2>&1
kubectl -n security delete secret openbao-restore-token --ignore-not-found > /dev/null 2>&1

retry 60 2 unsealed "$BAO_ADDR" || fail "OpenBao is not unsealed after the restore"
check "the admin from the snapshot logs in again (same password)" retry 15 2 admin_login
check "kv/workloads/demo is back, with its value" demo_restored
check "kv/$MARKER, written after the snapshot, is gone" marker_absent
check "the fresh init's root token died with the restore" denied as fresh bao token lookup
rm -f "$WORK/fresh.token"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

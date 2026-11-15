#!/bin/sh
# run-hook.sh <template-job> <run-name> [<bootstrap-config-map>]
#
# Runs one hook Job of the zitadel component the way Argo CD would: a fresh Job per run. The
# component's Jobs are applied suspended and never start; this takes the live one as a
# template, starts a copy named <run-name> and waits for it.
#
#   - one attempt (backoffLimit 0, restartPolicy Never), so a failing exit code is the
#     exit code of bootstrap.py and not the last of several retries;
#   - with a third argument the copy reads its bootstrap.yaml from that ConfigMap instead of
#     the tenant's (the variants of the verify Job).
#
# Prints the last lines of the main container's log, then exits with the container's exit code
# (124 on timeout). The log is public CI output: the bootstrap prints ids and outcomes, never
# a secret.
#
# Env: HOOK_TIMEOUT seconds (default 600), HOOK_LOG_TAIL lines (default 40).

set -eu

TEMPLATE="${1:?template job}"
NAME="${2:?run name}"
CONFIG="${3:-}"
TIMEOUT="${HOOK_TIMEOUT:-600}"
TAIL="${HOOK_LOG_TAIL:-40}"

kubectl delete job "$NAME" --ignore-not-found --wait > /dev/null

# Drop what the API server fills in (status, uid, selector, controller labels) so the copy is
# a new Job, not a clone of a running one.
kubectl get job "$TEMPLATE" -o json | jq --arg n "$NAME" --arg cm "$CONFIG" '
  del(.status, .metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp,
      .metadata.managedFields, .metadata.annotations, .spec.selector,
      .spec.ttlSecondsAfterFinished, .spec.template.metadata.creationTimestamp)
  | .metadata.name = $n
  | .metadata.labels |= ((. // {}) | with_entries(select(.key | test("controller-uid|job-name") | not)))
  | .metadata.labels["forjate.io/hook-run"] = "true"
  | .spec.template.metadata.labels |= ((. // {}) | with_entries(select(.key | test("controller-uid|job-name") | not)))
  | .spec.suspend = false
  | .spec.backoffLimit = 0
  | .spec.template.spec.restartPolicy = "Never"
  | if $cm != "" then (.spec.template.spec.volumes[] | select(.name == "bootstrap-config") | .configMap.name) = $cm else . end
' | kubectl create -f - > /dev/null

deadline=$(( $(date +%s) + TIMEOUT ))
status=Timeout
while [ "$(date +%s)" -lt "$deadline" ]; do
  conditions="$(kubectl get "job/$NAME" -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}' 2> /dev/null || true)"
  case "$conditions" in
    *Complete=True*) status=Complete; break ;;
    *Failed=True*) status=Failed; break ;;
  esac
  sleep 2
done

# The container that does the work: the one named like the template (zitadel-setup has a
# sidecar that comes first), else the first.
main="$(kubectl get "job/$NAME" -o jsonpath='{.spec.template.spec.containers[*].name}' | tr ' ' '\n' | grep -x "$TEMPLATE" || true)"
[ -n "$main" ] || main="$(kubectl get "job/$NAME" -o jsonpath='{.spec.template.spec.containers[0].name}')"
echo "--- $NAME ($status) ---"
kubectl logs "job/$NAME" -c "$main" --tail="$TAIL" 2>&1 || true
echo "--- end $NAME ---"

case "$status" in
  Complete) exit 0 ;;
  Timeout) exit 124 ;;
esac
# Failed: the exit code of the main container, or 1 when it never ran (an init container failed).
code="$(kubectl get pods -l "job-name=$NAME" -o jsonpath="{.items[0].status.containerStatuses[?(@.name==\"$main\")].state.terminated.exitCode}" 2> /dev/null || true)"
case "$code" in
  '' | 0 | *[!0-9]*) exit 1 ;;
  *) exit "$code" ;;
esac

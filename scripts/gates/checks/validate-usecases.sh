#!/usr/bin/env bash
# The contract matches the overlay: usecase.yaml validates, its name is the directory, every Job exists suspended.
source "$(dirname "$0")/_lib.sh"
c="${UC_DIR}/usecase.yaml"; [ -f "$c" ] || fail "no usecase.yaml"
"$PY" - "$c" "$REPO/scripts/ephemeral/usecase.schema.json" <<'PY' || fail "usecase.yaml does not validate against its schema"
import json, sys, yaml, jsonschema
doc = yaml.safe_load(open(sys.argv[1])); schema = json.load(open(sys.argv[2]))
jsonschema.validate(doc, schema)
PY
[ "$(yq -r .metadata.name "$c")" = "$UC_NAME" ] || fail "metadata.name != $UC_NAME"
m="$(mktemp -t gate-XXXXXX)"; kustomize_build "$UC_DIR" > "$m" || fail "root does not build"
for phase in seed run verify; do
  job="$(yq -r ".spec.jobs.$phase.name // \"\"" "$c")"; [ -n "$job" ] || continue
  n="$(yq ea -r "[select(.kind == \"Job\" and .metadata.name == \"$job\")] | length" "$m")"; [ "$n" -eq 1 ] || fail "Job $job ($phase) not in the built manifest"
  s="$(yq ea -r "[select(.kind == \"Job\" and .metadata.name == \"$job\")] | .[0].spec.suspend // false" "$m")"; [ "$s" = "true" ] || fail "Job $job must ship suspended"
done
pass "contract matches the overlay"

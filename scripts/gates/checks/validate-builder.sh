#!/usr/bin/env bash
# The use case's .builder artifacts validate (schemas, catalog, packs, cross-record consistency, gates).
source "$(dirname "$0")/_lib.sh"
"$PY" "$REPO/plugins/forjate/scripts/builder/validate.py" "$UC_DIR" && pass "validate.py clean" || fail "validate.py reported errors"

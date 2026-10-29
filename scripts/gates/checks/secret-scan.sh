#!/usr/bin/env bash
# No plaintext credential anywhere in the use case: generator literals, configs/, patches, env values, tracked .env.
source "$(dirname "$0")/_lib.sh"
out="$("$PY" "$REPO/plugins/forjate/scripts/builder/secret-scan.py" "$UC_DIR" 2>&1)"; rc=$?
echo "$out"
[ "$rc" -eq 0 ] && pass "secret-scan clean over ${UC_DIR#"$REPO"/}"
fail "secret-scan found plaintext credentials"

#!/usr/bin/env bash
# The scaffolded app matches the records: tool signatures, CI templates pinned to @v1, no hand-rolled build/push.
source "$(dirname "$0")/_lib.sh"
[ -d "${UC_DIR}/app" ] || skip "no app/ under the use case"
"$PY" "$REPO/plugins/forjate/scripts/builder/scaffold-check.py" "$UC_DIR" && pass "scaffold matches the records" || fail "scaffold-check reported findings"

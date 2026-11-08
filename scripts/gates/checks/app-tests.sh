#!/usr/bin/env bash
# The scaffolded app's unit tests pass (pytest in the app's own venv).
source "$(dirname "$0")/_lib.sh"
app="${UC_DIR}/app"; [ -f "$app/pyproject.toml" ] || skip "no app/ under the use case"
venv="$app/.venv"
[ -x "$venv/bin/python" ] || python3 -m venv "$venv" >/dev/null || fail "cannot create $venv"
"$venv/bin/pip" install -q -e "${app}[test]" >/dev/null 2>&1 || "$venv/bin/pip" install -q -e "$app" || fail "pip install failed"
log="$(mktemp -t app-tests-XXXXXX)"
( cd "$app" && "$venv/bin/python" -m pytest -q -p no:cacheprovider tests ${PYTEST_ARGS:-} ) >"$log" 2>&1; rc=$?
cat "$log"
if [ "$rc" -ne 0 ]; then
  # The verdict names the cause (a failed test, a collection error), not the warnings summary pytest prints last.
  why="$(grep -E '^(FAILED|ERROR) ' "$log" | head -2)"
  case "$why" in *" - "*) ;; *) why="${why}"$'\n'"$(grep -m1 -E '^E +' "$log")" ;; esac   # a collection error carries its message on an E line
  why="$(printf '%s\n' "$why" | sed -E '/^$/d; s/ +/ /g' | paste -sd';' -)"
  fail "app tests failed${why:+: $why}"
fi
rm -f "$log"
pass "app tests passed"

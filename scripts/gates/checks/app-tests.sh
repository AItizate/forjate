#!/usr/bin/env bash
# The scaffolded app's unit tests pass (pytest in the app's own venv).
source "$(dirname "$0")/_lib.sh"
app="${UC_DIR}/app"; [ -f "$app/pyproject.toml" ] || skip "no app/ under the use case"
venv="$app/.venv"
[ -x "$venv/bin/python" ] || python3 -m venv "$venv" >/dev/null || fail "cannot create $venv"
"$venv/bin/pip" install -q -e "${app}[test]" >/dev/null 2>&1 || "$venv/bin/pip" install -q -e "$app" || fail "pip install failed"
( cd "$app" && "$venv/bin/python" -m pytest -q -p no:cacheprovider tests ${PYTEST_ARGS:-} ) || fail "app tests failed"
pass "app tests passed"

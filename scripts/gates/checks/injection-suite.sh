#!/usr/bin/env bash
# The app's injection suite (tests marked injection) pass.
source "$(dirname "$0")/_lib.sh"
app="${UC_DIR}/app"; [ -f "$app/pyproject.toml" ] || skip "no app/ under the use case"
grep -rqE "pytest.mark.injection\b" "$app/tests" 2>/dev/null || skip "no tests marked 'injection' in app/tests"
PYTEST_ARGS="-m injection" exec bash "$(dirname "$0")/app-tests.sh"

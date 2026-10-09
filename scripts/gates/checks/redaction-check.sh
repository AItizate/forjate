#!/usr/bin/env bash
# The app's redaction tests (tests marked redaction) pass.
source "$(dirname "$0")/_lib.sh"
app="${UC_DIR}/app"; [ -f "$app/pyproject.toml" ] || skip "no app/ under the use case"
grep -rqE "pytest.mark.redaction\b" "$app/tests" 2>/dev/null || skip "no tests marked 'redaction' in app/tests"
PYTEST_ARGS="-m redaction" exec bash "$(dirname "$0")/app-tests.sh"

#!/usr/bin/env bash
# The app's golden-set regression (tests marked eval) pass.
source "$(dirname "$0")/_lib.sh"
app="${UC_DIR}/app"; [ -f "$app/pyproject.toml" ] || skip "no app/ under the use case"
grep -rqE "pytest.mark.eval\b" "$app/tests" 2>/dev/null || skip "no tests marked 'eval' in app/tests"
PYTEST_ARGS="-m eval" exec bash "$(dirname "$0")/app-tests.sh"

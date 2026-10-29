#!/usr/bin/env bash
# The stage's ArgoCD Application tracks a tag or commit with selfHeal true.
source "$(dirname "$0")/_lib.sh"
apps="$(grep -rlE '^kind: Application$' "$STAGE_DIR" 2>/dev/null || true)"
[ -n "$apps" ] || fail "no ArgoCD Application manifest under ${STAGE_DIR#"$REPO"/}"
bad=0
for f in $apps; do
  rev="$(yq -r '.spec.source.targetRevision // ""' "$f")"
  heal="$(yq -r '.spec.syncPolicy.automated.selfHeal // false' "$f")"
  [[ "$rev" =~ ^v?[0-9]+\.[0-9]+(\.[0-9]+)?([-+.][A-Za-z0-9.-]+)?$ || "$rev" =~ ^[0-9a-f]{7,40}$ ]] || { echo "  $f: targetRevision '$rev' is a branch"; bad=1; }
  [ "$heal" = "true" ] || { echo "  $f: selfHeal is $heal"; bad=1; }
done
[ "$bad" -eq 0 ] || fail "Application posture is the Crawl posture"
pass "Application(s) track a tag with selfHeal: true"

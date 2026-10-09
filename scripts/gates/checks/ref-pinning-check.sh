#!/usr/bin/env bash
# Every remote ?ref= in the stage overlay (and the root it extends) is a tag or a commit, never a branch.
source "$(dirname "$0")/_lib.sh"
bad=0; n=0
while IFS= read -r line; do
  ref="${line##*\?ref=}"; ref="${ref%%[\" ]*}"; n=$((n+1))
  if ! [[ "$ref" =~ ^v?[0-9]+\.[0-9]+(\.[0-9]+)?([-+.][A-Za-z0-9.-]+)?$ || "$ref" =~ ^[0-9a-f]{7,40}$ ]]; then echo "  branch ref: $line"; bad=1; fi
done < <(find "$UC_DIR" -path '*/.builder' -prune -o -path '*/app' -prune -o -name '*.yaml' -print0 2>/dev/null \
         | xargs -0 grep -hoE '[a-z+]+://[^ "]+\?ref=[^ "]+' 2>/dev/null | sort -u)
[ "$bad" -eq 0 ] || fail "remote references on a branch"
pass "$n remote reference(s), all pinned to a tag or commit"

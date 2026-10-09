#!/usr/bin/env bash
# Every stages/* overlay builds on its own and differs from the Crawl root.
source "$(dirname "$0")/_lib.sh"
root="$(mktemp -t gate-root-XXXXXX)"
kustomize_build "$UC_DIR" > "$root" 2>/dev/null || fail "the Crawl root does not build"
shopt -s nullglob
dirs=("$UC_DIR"/stages/*/)
[ ${#dirs[@]} -gt 0 ] || fail "no stages/ overlays exist"
for d in "${dirs[@]}"; do
  s="$(mktemp -t gate-stage-XXXXXX)"
  kustomize_build "$d" > "$s" 2> "${s}.err" || { cat "${s}.err"; fail "${d#"$REPO"/} does not build"; }
  cmp -s "$root" "$s" && fail "${d#"$REPO"/} builds to the same manifest as the Crawl root"
  echo "  ${d#"$UC_DIR"/} builds and differs from the root ($(grep -c '^kind:' "$s") resources)"
done
pass "${#dirs[@]} stage overlay(s) build and differ from the root"

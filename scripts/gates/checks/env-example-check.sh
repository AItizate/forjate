#!/usr/bin/env bash
# Every .env a secretGenerator reads and every sealed-*.yaml has a committed .env.example with the generate and seal recipe.
source "$(dirname "$0")/_lib.sh"
missing=0; checked=0
while IFS= read -r kfile; do
  dir="$(dirname "$kfile")"
  while IFS= read -r env; do
    [ -n "$env" ] || continue
    ex="${dir}/${env}.example"; checked=$((checked+1))
    [ -f "$ex" ] || { echo "  missing $ex"; missing=1; continue; }
    grep -q '^# To generate:' "$ex" || { echo "  $ex lacks '# To generate:' header"; missing=1; }
    grep -q '^# To seal:' "$ex" || { echo "  $ex lacks '# To seal:' header"; missing=1; }
  done < <(yq -r '(.secretGenerator // [])[] | (.envs // [])[]' "$kfile" 2>/dev/null)
done < <(find "$UC_DIR" -name kustomization.yaml -not -path '*/app/*')
while IFS= read -r sealed; do
  [ -n "$sealed" ] || continue
  base="$(basename "$sealed" .yaml)"; base="${base#sealed-}"; checked=$((checked+1))
  ex="$(dirname "$sealed")/${base}.env.example"
  [ -f "$ex" ] || { echo "  missing $ex for $sealed"; missing=1; continue; }
  grep -q '^# To seal:' "$ex" || { echo "  $ex lacks '# To seal:' header"; missing=1; }
done < <(find "$UC_DIR" -name 'sealed-*.yaml')
if git -C "$UC_DIR" ls-files --error-unmatch -- '*.env' >/dev/null 2>&1; then echo "  a .env file is tracked by git"; missing=1; fi
[ "$missing" -eq 0 ] || fail "secrets without a complete .env.example recipe"
pass "$checked secret(s) carry a .env.example with the generate and seal commands"

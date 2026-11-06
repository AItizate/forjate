#!/usr/bin/env bash
# Source it; do not run it. The pinned toolchain, for local runs.
#
#   source scripts/toolchain/toolchain.sh
#   toolchain_path          # puts .tools/bin (scripts/toolchain/install.sh) first on PATH
#   toolchain_check yq      # exit 0 when `yq` is the version .github/toolchain.env pins
#
# A different version is refused (exit 1) with the install command. FORJATE_TOOLCHAIN=warn
# downgrades the refusal to a warning for a run where the difference does not matter.
# CI installs the pinned version itself, so there the check always passes.

TOOLCHAIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOLCHAIN_ENV="${TOOLCHAIN_ROOT}/.github/toolchain.env"

toolchain_path() {
  case ":${PATH}:" in
    *":${TOOLCHAIN_ROOT}/.tools/bin:"*) ;;
    *) [ -d "${TOOLCHAIN_ROOT}/.tools/bin" ] && export PATH="${TOOLCHAIN_ROOT}/.tools/bin:${PATH}" ;;
  esac
  return 0
}

# toolchain_pinned <tool> → the pinned version on stdout, empty when the file or the pin is missing
toolchain_pinned() {
  local var; var="$(printf '%s_VERSION' "$1" | tr '[:lower:]' '[:upper:]')"
  [ -f "$TOOLCHAIN_ENV" ] || return 0
  sed -n "s/^${var}=//p" "$TOOLCHAIN_ENV" | head -1
}

# toolchain_version <tool> → the version the binary on PATH reports, without the leading v
toolchain_version() {
  case "$1" in
    yq) yq --version 2>/dev/null | sed -n 's/.*version v\{0,1\}\([0-9][0-9.]*\).*/\1/p' | head -1 ;;
    *)  return 1 ;;
  esac
}

toolchain_check() {
  local tool="$1" want have
  want="$(toolchain_pinned "$tool")"
  [ -n "$want" ] || return 0   # no pin recorded (an older factory checkout): nothing to compare against
  have="$(toolchain_version "$tool" || true)"
  if [ "$have" = "$want" ]; then return 0; fi
  local what="${have:+is ${have}}"; what="${what:-is not installed}"
  local msg="${tool} ${what}, CI pins ${want} (.github/toolchain.env). Install it with: ${TOOLCHAIN_ROOT}/scripts/toolchain/install.sh"
  if [ "${FORJATE_TOOLCHAIN:-}" = "warn" ]; then
    echo "WARNING: ${msg}" >&2
    return 0
  fi
  echo "ERROR: ${msg}  (FORJATE_TOOLCHAIN=warn runs anyway)" >&2
  return 1
}

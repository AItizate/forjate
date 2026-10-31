#!/usr/bin/env bash
# Install the tool versions .github/toolchain.env pins into .tools/bin (git-ignored), where
# scripts/toolchain/toolchain.sh finds them before anything else on PATH. Your own yq is not touched.
#
#   scripts/toolchain/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=toolchain.sh
source "${ROOT}/scripts/toolchain/toolchain.sh"

version="$(toolchain_pinned yq)"
[ -n "$version" ] || { echo "no YQ_VERSION in ${TOOLCHAIN_ENV}" >&2; exit 1; }

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  arm64|aarch64) arch=arm64 ;;
  *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

dest="${ROOT}/.tools/bin"
if PATH="${dest}:${PATH}" toolchain_version yq 2>/dev/null | grep -qx "$version" && [ -x "${dest}/yq" ]; then
  echo "yq ${version} already in ${dest}"
  exit 0
fi

# A fresh directory: the download is untrusted until it reports the pinned version.
tmp="$(mktemp -d -t forjate-toolchain-XXXXXX)"
trap 'rm -rf "$tmp"' EXIT
url="https://github.com/mikefarah/yq/releases/download/v${version}/yq_${os}_${arch}"
echo "downloading ${url}"
curl -fsSL -o "${tmp}/yq" "$url"
chmod +x "${tmp}/yq"
got="$(cd "$tmp" && ./yq --version | sed -n 's/.*version v\{0,1\}\([0-9][0-9.]*\).*/\1/p')"
[ "$got" = "$version" ] || { echo "downloaded yq reports '${got}', expected ${version}" >&2; exit 1; }

mkdir -p "$dest"
mv "${tmp}/yq" "${dest}/yq"
echo "yq ${version} installed in ${dest}"

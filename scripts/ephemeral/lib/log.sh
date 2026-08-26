#!/usr/bin/env bash
# =============================================================================
# log.sh — Shared logging helpers for the ephemeral use-case runner.
#
# Source this file; do not execute it. Consolidates the colour/log block that
# is currently copy-pasted across the overlay bootstrap scripts.
# =============================================================================

# Colours are disabled when stdout is not a TTY (CI logs, redirected output).
if [ -t 1 ]; then
  C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'; C_RED='\033[0;31m'
  C_BLUE='\033[0;34m';  C_BOLD='\033[1m';      C_RESET='\033[0m'
else
  C_GREEN=''; C_YELLOW=''; C_RED=''; C_BLUE=''; C_BOLD=''; C_RESET=''
fi

log()   { echo -e "${C_GREEN}[✓]${C_RESET} $*"; }
info()  { echo -e "${C_BLUE}[→]${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}[!]${C_RESET} $*"; }
error() { echo -e "${C_RED}[✗]${C_RESET} $*" >&2; exit 1; }

# Section header, for separating lifecycle phases in a long `up` run.
section() {
  echo ""
  echo -e "${C_BOLD}── $* ${C_RESET}"
}

# Horizontal rule used around captured Job logs.
rule() {
  echo "────────────────────────────────────────────────────────────"
}

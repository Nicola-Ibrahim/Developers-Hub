#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SHELL_DIR="${SCRIPT_DIR}/shell"
source "${SHELL_DIR}/menu.sh"
source "${SHELL_DIR}/docker.sh"

usage() {
  cat <<'USAGE'
Usage:
  scripts/dev.sh [menu]
  scripts/dev.sh help
  scripts/dev.sh up
  scripts/dev.sh down | status | logs SERVICE
  scripts/dev.sh backend | frontend
  scripts/dev.sh clean [--apply]

With no arguments, the interactive menu starts when stdin is a TTY; otherwise
help is shown. Docker commands require a local Docker Engine/Desktop and Compose
v2. Native backend and frontend commands require their dependencies and configured
local services. Native startup does not install dependencies or apply migrations.
Docker startup runs the configured migration job.
USAGE
}

fail() { printf 'Error: %s\n' "$1" >&2; return "${2:-1}"; }

source "${SHELL_DIR}/cleanup.sh"
source "${SHELL_DIR}/dev-docker.sh"
source "${SHELL_DIR}/native.sh"

if [[ $# -eq 0 ]]; then
  if [[ -t 0 ]]; then set -- menu; else usage; exit 0; fi
fi
command_name="$1"
shift
cd "$REPO_ROOT"

case "$command_name" in
  help|--help|-h) usage ;;
  menu)
    [[ $# -eq 0 ]] || { fail 'menu takes no options' 2; exit $?; }
    dev_menu
    ;;
  up|down|status|logs) docker_cli "$command_name" "$@" ;;
  backend) [[ $# -eq 0 ]] || { fail 'backend takes no options' 2; exit $?; }; native_backend ;;
  frontend) [[ $# -eq 0 ]] || { fail 'frontend takes no options' 2; exit $?; }; native_frontend ;;
  clean) cleanup_cli "$@" ;;
  *) usage >&2; fail "unknown command: $command_name" 2; exit $? ;;
esac

#!/usr/bin/env bash
# Local PostgreSQL migration menu and direct commands. Compatible with Bash 3.2.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/shell/menu.sh"
source "$SCRIPT_DIR/shell/docker.sh"
source "$SCRIPT_DIR/shell/database.sh"
db_main "$@"

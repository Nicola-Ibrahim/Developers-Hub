#!/usr/bin/env bash
# Foreground native development servers and top-level menu.

native_backend() {
  python3 "${REPO_ROOT}/scripts/helpers/local_database.py" --target host --root "$REPO_ROOT" --native >/dev/null || {
    printf 'Backend prerequisites are not configured. Configure loopback PostgreSQL and OPA, and set the token pepper; see docs/platform-dev.md.\n' >&2
    return 1
  }
  cd "$REPO_ROOT/backend" || return 1
  UV_PYTHON_DOWNLOADS=never uv run --offline --frozen --no-sync --no-env-file fastapi dev --host 127.0.0.1 --port 8000 || {
    printf 'Backend launch failed. If its locked environment is missing, run uv sync --frozen from backend, then retry.\n' >&2
    return 1
  }
}

native_frontend() {
  cd "$REPO_ROOT/frontend" || return 1
  BACKEND_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 || {
    printf 'Frontend launch failed. Ensure Node.js dependencies are installed and the backend is available at http://127.0.0.1:8000.\n' >&2
    return 1
  }
}

native_menu_action() {
  case "$1" in backend) native_backend ;; frontend) native_frontend ;; esac
}

native_menu() {
  local choice
  while true; do
    menu_choose 'Native development' 'Backend API (local PostgreSQL + OPA)' 'Frontend dashboard (host API)'
    choice="$MENU_CHOICE"
    case "$choice" in
      quit|back) return 0 ;;
      1) menu_run native_menu_action backend ;;
      2) menu_run native_menu_action frontend ;;
    esac
    [[ "${MENU_QUIT:-0}" != 1 ]] || return 0
  done
}

dev_menu() {
  local choice
  while true; do
    menu_choose 'Development' 'Local Docker services' 'Native backend / frontend' 'Database management' 'Cache cleanup' 'Help and commands'
    choice="$MENU_CHOICE"
    case "$choice" in
      quit) return 0 ;;
      back) return 0 ;;
      1) docker_menu; [[ "${MENU_QUIT:-0}" != 1 ]] || return 0 ;;
      2) native_menu; [[ "${MENU_QUIT:-0}" != 1 ]] || return 0 ;;
      3) database_menu || printf 'Database menu returned an error.\n' >&2 ;;
      4) menu_run cleanup_menu ;;
      5) usage ;;
    esac
    [[ "${MENU_QUIT:-0}" != 1 ]] || return 0
  done
}

database_menu() {
  source "${SCRIPT_DIR}/shell/database.sh"
  db_menu
}

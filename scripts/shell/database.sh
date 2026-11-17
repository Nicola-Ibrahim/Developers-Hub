#!/usr/bin/env bash
# Local database operations shared by the Dev and DB entrypoints.
# Sourcing defines functions only; credentials are never loaded by sourcing.

db_usage() {
  cat <<'EOF'
Usage:
  scripts/db.sh menu
  scripts/db.sh compose|host status|current|heads|history|branches|check|sql|upgrade [--yes]
  scripts/db.sh host blank-revision --message MESSAGE [--yes]
  scripts/db.sh host autogenerate-revision --message MESSAGE [--yes]
  scripts/db.sh host revision --message MESSAGE [--autogenerate] [--yes]

With no arguments, the menu opens only when stdin is a terminal.
The sql action prints an upgrade-to-head SQL preview and never applies it.
EOF
}

db_fail() { printf 'Error: %s\n' "$1" >&2; return 2; }

db_validate_args() {
  TARGET="${1:-}"
  ACTION="${2:-}"
  YES=0
  MESSAGE=""
  AUTOGENERATE=0
  if [[ "$TARGET" != "compose" && "$TARGET" != "host" ]]; then db_fail "target must be compose or host"; return 1; fi
  if [[ "$ACTION" == "blank-revision" || "$ACTION" == "autogenerate-revision" || "$ACTION" == "revision" ]]; then
    [[ "$TARGET" == "host" ]] || { db_fail "revision creation is available only for host execution"; return 1; }
    shift 2
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --message)
          [[ $# -ge 2 && -n "$2" ]] || { db_fail "--message requires a value"; return 1; }
          MESSAGE="$2"; shift 2 ;;
        --autogenerate) AUTOGENERATE=1; shift ;;
        --yes) YES=1; shift ;;
        *) db_fail "unsupported revision option"; return 1 ;;
      esac
    done
    [[ -n "$MESSAGE" ]] || { db_fail "revision requires --message MESSAGE"; return 1; }
    if [[ $YES -ne 1 && $MENU_MODE -ne 1 && ! -t 0 ]]; then
      db_fail "noninteractive revisions require --yes"; return 1
    fi
    return 0
  fi
  case "$ACTION" in status|current|heads|history|branches|check|sql|upgrade) ;; *) db_fail "action must be status, current, heads, history, branches, check, sql, upgrade, or a host revision action"; return 1 ;; esac
  shift 2
  if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--yes" ) ]]; then
    db_fail "only --yes is supported for this action"; return 1
  fi
  [[ $# -eq 0 ]] || YES=1
  if [[ "$ACTION" != "upgrade" && $YES -eq 1 ]]; then db_fail "--yes applies only to upgrade"; return 1; fi
  return 0
}

db_validate_local() {
  python3 "$SCRIPT_DIR/helpers/local_database.py" --target "$TARGET" --root "$REPO_ROOT"
}

db_host_alembic() (
  cd "$REPO_ROOT/backend" || exit 1
  if [[ -n "${PLATFORM_DATABASE_URL_FILE:-}${DATABASE_URL_FILE:-}" ]]; then
    unset PLATFORM_DATABASE_URL DATABASE_URL
  fi
  UV_PYTHON_DOWNLOADS=never uv run --offline --no-env-file --frozen --no-sync alembic "$@"
)

db_compose_alembic() {
  require_local_docker || return $?
  local_compose run --rm --no-deps --pull never migrate alembic "$@"
}

db_invoke_alembic() {
  if [[ "$TARGET" == host ]]; then db_host_alembic "$@"; else db_compose_alembic "$@"; fi
}

db_run_action() {
  local operation="$ACTION"
  if [[ "$operation" == "blank-revision" || "$operation" == "autogenerate-revision" || "$operation" == "revision" ]]; then
    local args=(revision --message "$MESSAGE")
    if [[ "$operation" == "autogenerate-revision" || ( "$operation" == "revision" && $AUTOGENERATE -eq 1 ) ]]; then args+=(--autogenerate); fi
    if [[ $YES -ne 1 ]]; then
      if [[ $MENU_MODE -ne 1 && ! -t 0 ]]; then
        db_fail "noninteractive revisions require --yes"
        return 2
      fi
      if ! menu_confirm "Create this migration revision in backend/migrations/versions?"; then
        return 0
      fi
      [[ "${MENU_QUIT:-0}" != 1 ]] || return 0
    fi
    db_validate_local || return $?
    db_host_alembic "${args[@]}"
    return $?
  fi

  if [[ "$operation" == "upgrade" && $YES -ne 1 ]]; then
    if [[ $MENU_MODE -ne 1 && ! -t 0 ]]; then
      db_fail "noninteractive upgrades require --yes"
      return 2
    fi
    if ! menu_confirm "Upgrade the $TARGET PostgreSQL database to Alembic head?"; then
      return 0
    fi
    [[ "${MENU_QUIT:-0}" != 1 ]] || return 0
  fi
  printf 'Target: %s | Action: %s\n' "$TARGET" "$operation" >&2
  db_validate_local || return $?
  case "$operation" in
    status) db_invoke_alembic current && db_invoke_alembic heads ;;
    current) db_invoke_alembic current ;;
    heads) db_invoke_alembic heads ;;
    history) db_invoke_alembic history --verbose ;;
    branches) db_invoke_alembic branches --verbose ;;
    check) db_invoke_alembic check ;;
    sql) db_invoke_alembic upgrade head --sql ;;
    upgrade) db_invoke_alembic upgrade head ;;
  esac
}

db_menu() {
  local selected_target="" selected_action=""
  MENU_MODE=1
  YES=0; MESSAGE=""; AUTOGENERATE=0
  while true; do
    if [[ -z "$selected_target" ]]; then
      menu_choose "Database management" "Compose" "Host (uv)"
      case "$MENU_CHOICE" in
        1) selected_target=compose ;;
        2) selected_target=host ;;
        back|quit) return 0 ;;
      esac
    fi
    if [[ "$selected_target" == host ]]; then
      menu_choose "Database management / Host" \
        "Status (current and heads)" "History" "Branches" "Check model drift" \
        "SQL preview (upgrade head --sql)" "Heads" "Upgrade to head" \
        "Create blank migration" "Autogenerate migration"
    else
      menu_choose "Database management / Compose" \
        "Status (current and heads)" "History" "Branches" "Check model drift" \
        "SQL preview (upgrade head --sql)" "Heads" "Upgrade to head"
    fi
    selected_action="$MENU_CHOICE"
    case "$selected_action" in
      back) selected_target=""; continue ;;
      quit) return 0 ;;
      1) TARGET="$selected_target"; ACTION=status; YES=0; menu_run db_run_action ;;
      2) TARGET="$selected_target"; ACTION=history; YES=0; menu_run db_run_action ;;
      3) TARGET="$selected_target"; ACTION=branches; YES=0; menu_run db_run_action ;;
      4) TARGET="$selected_target"; ACTION=check; YES=0; menu_run db_run_action ;;
      5) TARGET="$selected_target"; ACTION=sql; YES=0; menu_run db_run_action ;;
      6) TARGET="$selected_target"; ACTION=heads; YES=0; menu_run db_run_action ;;
      7) TARGET="$selected_target"; ACTION=upgrade; YES=0; menu_run db_run_action ;;
      8|9)
        if [[ "$selected_target" == host ]]; then
          TARGET=host; YES=0
          if [[ "$selected_action" == 8 ]]; then ACTION=blank-revision; else ACTION=autogenerate-revision; fi
          if menu_text "Migration message"; then
            MESSAGE="$MENU_TEXT"
            menu_run db_run_action
          fi
        fi
        ;;
      *) return 0 ;;
    esac
    [[ "${MENU_QUIT:-0}" != 1 ]] || return 0
  done
}

db_main() {
  MENU_MODE=0
  if [[ $# -eq 0 ]]; then
    if [[ -t 0 ]]; then db_menu; else db_usage; fi
  elif [[ $# -eq 1 && "$1" == menu ]]; then
    db_menu
  elif [[ $# -eq 1 && ( "$1" == --help || "$1" == -h || "$1" == help ) ]]; then
    db_usage
  else
    db_validate_args "$@" || return $?
    db_run_action
  fi
}

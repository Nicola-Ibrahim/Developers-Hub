#!/usr/bin/env bash
# Local Compose operations and interactive service routing.

docker_start() {
  [[ $# -eq 0 ]] || { fail 'up takes no options' 2; return $?; }
  require_local_docker || return 1
  python3 "${REPO_ROOT}/scripts/helpers/init_env.py" || { fail 'Local environment initialization failed.'; return 1; }
  local_compose up --build -d --wait --remove-orphans || { fail 'Compose startup/readiness failed (including migration completion).'; return 1; }
  printf 'Core services passed Compose readiness. Dashboard: http://127.0.0.1:3000; API: http://127.0.0.1:8000/health/ready\n'
}

docker_cli() {
  local action="$1"; shift
  case "$action" in
    up) docker_start "$@" ;;
    down)
      [[ $# -eq 0 ]] || { fail 'down takes no options' 2; return $?; }
      require_local_docker && local_compose down --remove-orphans || { fail 'Compose shutdown failed.'; return 1; } ;;
    status)
      [[ $# -eq 0 ]] || { fail 'status takes no options' 2; return $?; }
      require_local_docker && local_compose ps api frontend postgres opa migrate || { fail 'Could not read Compose status.'; return 1; } ;;
    logs)
      [[ $# -eq 1 ]] || { fail 'logs requires exactly one allowlisted service' 2; return $?; }
      case "$1" in api|frontend|migrate|opa|postgres) ;; *) fail "service is not allowlisted: $1" 2; return $? ;; esac
      require_local_docker && local_compose logs --follow "$1" || { fail 'Could not read service logs.'; return 1; } ;;
  esac
}

docker_menu() {
  local choice selected index
  local -a services
  services=(api frontend postgres opa migrate)
  while true; do
    menu_choose 'Local Docker' 'Start core services' 'Stop services' 'Service status' 'Follow service logs'
    choice="$MENU_CHOICE"
    case "$choice" in
      quit|back) return 0 ;;
      1)
        menu_run docker_start ;;
      2) menu_run docker_cli down ;;
      3) menu_run docker_cli status ;;
      4)
        menu_choose 'Choose a service' api frontend postgres opa migrate
        selected="$MENU_CHOICE"
        case "$selected" in
          quit) return 0 ;;
          back) continue ;;
          *) index=$((selected - 1)); menu_run docker_cli logs "${services[$index]}" ;;
        esac ;;
    esac
  done
}

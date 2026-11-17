#!/usr/bin/env bash
# Shared local Docker guard; no Docker call occurs when sourced.
require_local_docker() {
  local endpoint
  command -v docker >/dev/null 2>&1 || { printf 'Error: Docker CLI is unavailable.\n' >&2; return 1; }
  if [[ -n "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]]; then
    endpoint="$DOCKER_HOST"
  else
    endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')" || { printf 'Error: Could not resolve Docker context.\n' >&2; return 1; }
  fi
  case "$endpoint" in
    unix://*) ;;
    *) printf 'Error: This command is local-only; select a Unix-socket Docker context.\n' >&2; return 1 ;;
  esac
  docker info >/dev/null 2>&1 || { printf 'Error: Docker daemon is unavailable.\n' >&2; return 1; }
}

local_compose() (
  unset COMPOSE_FILE COMPOSE_PROFILES COMPOSE_PROJECT_NAME COMPOSE_ENV_FILES
  docker compose --env-file /dev/null --file "$REPO_ROOT/compose.yaml" --project-directory "$REPO_ROOT" --project-name devops-hub "$@"
)

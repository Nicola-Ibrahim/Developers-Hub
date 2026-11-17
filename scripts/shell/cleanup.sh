#!/usr/bin/env bash
# Cache cleanup operations. Paths are intentionally fixed and symlink checked.

cleanup_caches() {
  local apply="$1" cache target part path_parts
  for cache in .pytest_cache .mypy_cache .ruff_cache backend/.pytest_cache frontend/.next/cache scripts/.pytest_cache; do
    target="${REPO_ROOT}"
    path_parts="${cache//\// }"
    for part in $path_parts; do
      target="${target}/${part}"
      [[ -L "$target" ]] && { printf 'Error: refusing symlink cache path: %s\n' "$cache" >&2; return 1; }
    done
    if [[ -e "$target" ]]; then
      [[ -d "$target" ]] || { printf 'Error: refusing non-directory cache path: %s\n' "$cache" >&2; return 1; }
      if [[ "$apply" == 1 ]]; then
        printf 'Remove %s\n' "$cache"
        rm -rf -- "$target" || { printf 'Error: could not remove cache: %s\n' "$cache" >&2; return 1; }
      else
        printf 'Would remove %s\n' "$cache"
      fi
    fi
  done
}

cleanup_cli() {
  local apply=0
  if [[ $# -gt 1 ]]; then fail 'clean accepts only optional --apply' 2; return $?; fi
  if [[ $# -eq 1 ]]; then
    [[ "$1" == --apply ]] || { fail 'clean accepts only optional --apply' 2; return $?; }
    apply=1
  fi
  cleanup_caches "$apply"
}

cleanup_menu() {
  printf 'Approved cache paths that exist:\n'
  cleanup_caches 0 || return 1
  if menu_confirm 'Remove these cache directories?'; then
    cleanup_caches 1
  else
    printf 'Cleanup cancelled.\n'
  fi
}

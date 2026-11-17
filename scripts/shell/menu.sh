#!/usr/bin/env bash
# Shared Bash 3.2 menu primitives. Sourcing this file has no side effects.

menu__colors() {
  MENU_COLOR=0
  if [[ -t 2 && "${TERM:-}" != dumb && -z "${NO_COLOR+x}" ]]; then
    MENU_COLOR=1
  fi
}

menu__paint() {
  local code="$1" text="$2"
  if [[ "${MENU_COLOR:-0}" == 1 ]]; then
    printf '\033[%sm%s\033[0m' "$code" "$text" >&2
  else
    printf '%s' "$text" >&2
  fi
}

menu_choose() {
  local title="$1" display_title choice index label description left_width width line top middle bottom
  shift
  menu__colors
  while true; do
    width=${COLUMNS:-72}
    [[ "$width" =~ ^[0-9]+$ ]] || width=72
    (( width < 44 )) && width=44
    (( width > 100 )) && width=100
    case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in *UTF-8*|*utf8*)
      if [[ -t 2 && "${TERM:-}" != dumb ]]; then
        top='╔'; middle='║'; bottom='╚'; line='═'
      else top='+'; middle='|'; bottom='+'; line='-'; fi ;;
      *) top='+'; middle='|'; bottom='+'; line='-' ;;
    esac
    width=$((width - 4))
    case "$title" in
      DevOps\ Hub*|Devops\ Hub*|DEVOPS\ HUB*) display_title="$title" ;;
      *) display_title="DEVOPS HUB | $title" ;;
    esac
    display_title=${display_title:0:$((width - 2))}
    printf '\n' >&2
    printf -v top '%*s' "$width" ''
    printf -v bottom '%*s' "$width" ''
    if [[ "$line" == '═' ]]; then
      top="${top// /═}"; bottom="${bottom// /═}"
      menu__paint '1;36' "  ╔${top}╗"; printf '\n' >&2
      printf -v middle '%-*s' "$((width - 2))" "$display_title"
      menu__paint '1;36' "  ║ $middle ║"; printf '\n' >&2
      menu__paint '1;36' "  ╚${bottom}╝"; printf '\n' >&2
    else
      top="${top// /-}"; bottom="${bottom// /-}"
      menu__paint '1;36' "  +${top}+"; printf '\n' >&2
      printf -v middle '%-*s' "$((width - 2))" "$display_title"
      menu__paint '1;36' "  | $middle |"; printf '\n' >&2
      menu__paint '1;36' "  +${bottom}+"; printf '\n' >&2
    fi
    left_width=0
    for label in "$@"; do
      description=${label#*|}
      [[ "$description" == "$label" ]] && description=''
      label=${label%%|*}
      (( ${#label} > left_width )) && left_width=${#label}
    done
    index=1
    for label in "$@"; do
      description=${label#*|}
      [[ "$description" == "$label" ]] && description=''
      label=${label%%|*}
      menu__paint '1;36' '  '
      menu__paint '1;36' "$index)"
      printf '  %-*s' "$left_width" "$label" >&2
      if [[ -n "$description" ]]; then
        menu__paint '2' '  /  '
        printf '%s' "$description" >&2
      fi
      printf '\n' >&2
      index=$((index + 1))
    done
    menu__paint '2' '  ----------------------------------------------------------------'
    printf '\n' >&2
    menu__paint '1;32' '  b)'
    printf ' Back   ' >&2
    menu__paint '1;31' 'q)'
    printf ' Quit (or press Enter)\n' >&2
    printf '  Select a number; invalid choices can be entered again.\n\n' >&2
    menu__paint '1;33' 'Your choice: '
    if ! IFS= read -r choice; then MENU_CHOICE=quit; MENU_QUIT=1; return 0; fi
    case "$choice" in
      ''|q|Q|quit|exit) MENU_CHOICE=quit; MENU_QUIT=1; return 0 ;;
      b|B|back|0) MENU_CHOICE=back; return 0 ;;
    esac
    index=1
    for label in "$@"; do
      if [[ "$choice" == "$index" ]]; then MENU_CHOICE="$index"; return 0; fi
      index=$((index + 1))
    done
    menu__paint '1;31' 'Invalid choice. Enter a listed number, b, or q.'
    printf '\n' >&2
  done
}

menu_confirm() {
  local answer
  menu__colors
  while true; do
    menu__paint '1;33' "$1 [y/N, b to cancel]: "
    if ! IFS= read -r answer; then MENU_QUIT=1; MENU_CANCELLED=1; return 1; fi
    case "$answer" in
      y|Y|yes) MENU_CANCELLED=0; return 0 ;;
      ''|n|N|no|b|B|back) MENU_CANCELLED=1; return 1 ;;
      q|Q|quit|exit) MENU_QUIT=1; MENU_CANCELLED=1; return 1 ;;
      *) menu__paint '1;31' 'Please enter y or n; enter b to cancel.'; printf '\n' >&2 ;;
    esac
  done
}

menu_text() {
  local answer
  menu__colors
  while true; do
    menu__paint '1;33' "$1 (b to cancel): "
    if ! IFS= read -r answer; then MENU_QUIT=1; return 1; fi
    case "$answer" in
      b|B|back) return 1 ;;
      q|Q|quit|exit) MENU_QUIT=1; return 1 ;;
    esac
    if [[ -n "${answer//[[:space:]]/}" ]]; then MENU_TEXT="$answer"; return 0; fi
    menu__paint '1;31' 'A value is required. Try again or enter b.'
    printf '\n' >&2
  done
}

menu_run() {
  local result original_pwd
  original_pwd=$PWD
  MENU_CANCELLED=0
  # Call directly so an action's MENU_QUIT decision survives. The conditional
  # keeps a failed action from terminating the caller under `set -e`.
  if "$@"; then result=0; else result=$?; fi
  if [[ "${MENU_QUIT:-0}" == 1 ]]; then
    :
  elif [[ "${MENU_CANCELLED:-0}" == 1 ]]; then
    menu__paint '1;33' 'Action cancelled.'
    printf '\n' >&2
  elif [[ "$result" == 0 ]]; then
    menu__paint '1;32' 'Action finished.'
    printf '\n' >&2
  else
    menu__paint '1;31' "Action failed (exit $result). Correct the problem and choose again."
    printf '\n' >&2
  fi
  cd "$original_pwd" || return 1
  return 0
}

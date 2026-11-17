#!/usr/bin/env bash
set -euo pipefail

pattern='^(build|ci|chore|docs|feat|fix|perf|refactor|revert|test)(\([a-zA-Z0-9/_-]+\))?(!)?: .{1,100}$'

usage() {
  echo "usage: $0 (--subject TEXT | --file PATH | --range BASE..HEAD)" >&2
  exit 2
}

check_subject() {
  if [[ ! "$1" =~ $pattern ]]; then
    printf 'not a conventional commit subject: "%s"\n' "$1" >&2
    return 1
  fi
}

case "${1:-}" in
--subject)
  [ $# -eq 2 ] || usage
  subject="$(printf '%s' "$2" | sed -E 's/ \(#[0-9]+\)$//')"
  check_subject "$subject"
  ;;
--file)
  [ $# -eq 2 ] || usage
  subject="$(grep -vE '^(#|$)' "$2" | sed -n '1p' | sed -E 's/ \(#[0-9]+\)$//')"
  check_subject "$subject"
  ;;
--range)
  [ $# -eq 2 ] || usage
  status=0
  mapfile -t subjects < <(git log --format='%s' "$2")
  for subject in "${subjects[@]}"; do
    check_subject "$(printf '%s' "$subject" | sed -E 's/ \(#[0-9]+\)$//')" || status=1
  done
  exit "$status"
  ;;
*)
  usage
  ;;
esac

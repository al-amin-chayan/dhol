#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/eof-marker.sh start
  scripts/eof-marker.sh finish [--start <unix-epoch>] --status <status>

Statuses: DONE, IN PROGRESS, BLOCKED, NEEDS HUMAN ACTION
EOF
}

case "${1:-}" in
  start)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    date +%s
    ;;
  finish)
    shift
    start_epoch=""
    status=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --start)
          [ "$#" -ge 2 ] || { usage; exit 2; }
          start_epoch="$2"
          shift 2
          ;;
        --status)
          [ "$#" -ge 2 ] || { usage; exit 2; }
          status="$2"
          shift 2
          ;;
        *)
          usage
          exit 2
          ;;
      esac
    done

    case "$status" in
      DONE|"IN PROGRESS"|BLOCKED|"NEEDS HUMAN ACTION") ;;
      *)
        printf 'error: invalid or missing status\n' >&2
        usage
        exit 2
        ;;
    esac

    now_epoch="$(date +%s)"
    timestamp="$(LC_ALL=C TZ=Asia/Dhaka date '+%b %d, %Y | %I:%M %p')"
    duration="unavailable"
    if [ -n "$start_epoch" ]; then
      case "$start_epoch" in
        *[!0-9]*|'')
          printf 'error: --start must be a non-negative Unix epoch\n' >&2
          exit 2
          ;;
      esac
      if [ "$start_epoch" -gt "$now_epoch" ]; then
        printf 'error: --start cannot be in the future\n' >&2
        exit 2
      fi
      elapsed=$((now_epoch - start_epoch))
      if [ "$elapsed" -lt 60 ]; then
        duration="${elapsed}s"
      else
        duration="$((elapsed / 60))m $(printf '%02d' "$((elapsed % 60))")s"
      fi
    fi

    printf '%s\n' \
      "--- EOF @ $timestamp | Duration: $duration | Status: $status ---"
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac

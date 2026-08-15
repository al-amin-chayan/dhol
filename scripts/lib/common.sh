#!/usr/bin/env bash

dholbeat_die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

dholbeat_repo_root() {
  local caller_path="$1"
  local caller_dir
  caller_dir="$(CDPATH='' cd -- "$(dirname -- "$caller_path")" && pwd -P)"
  (CDPATH='' cd -- "$caller_dir/.." && pwd -P)
}

dholbeat_require_command() {
  command -v "$1" >/dev/null 2>&1 || dholbeat_die "required command not found: $1"
}

dholbeat_yaml_scalar() {
  local path="$1"
  local key="$2"
  awk -v wanted="${key}:" '
    $1 == wanted {
      $1 = ""
      sub(/^[[:space:]]+/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$path"
}

dholbeat_sha256_files() {
  local root="$1"
  shift
  {
    local relative
    for relative in "$@"; do
      printf '%s\0' "$relative"
      command cat "$root/$relative"
      printf '\0'
    done
  } | if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  else
    dholbeat_die "sha256sum or shasum is required to lock the controller source"
  fi
}

dholbeat_human_bytes() {
  awk -v bytes="$1" 'BEGIN {
    split("B KiB MiB GiB TiB", units, " ")
    value = bytes + 0
    unit = 1
    while (value >= 1024 && unit < 5) {
      value /= 1024
      unit++
    }
    printf "%.1f %s", value, units[unit]
  }'
}

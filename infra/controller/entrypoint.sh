#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${HOME}" "${ANSIBLE_LOCAL_TEMP}"

if [ "${1:-}" = "versions" ]; then
  exec python /opt/dholbeat/runtime_versions.py
fi

if [ "$#" -eq 0 ]; then
  exec python /opt/dholbeat/runtime_versions.py
fi

exec "$@"

#!/usr/bin/env bash
# Mint a fresh GitHub App installation token for the agent running this command.
# Personal profiles live outside repositories in ~/.config/github-agent-apps/.
set -euo pipefail
umask 077

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

repo_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)"
lane_agent=""
runtime_agent=""

if [ -f "$repo_root/.dholbeat-agent" ]; then
  IFS= read -r lane_agent <"$repo_root/.dholbeat-agent" || true
fi

if [ -n "${CODEX_THREAD_ID:-}" ] || [ -n "${CODEX_CI:-}" ]; then
  runtime_agent="codex"
fi
if [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]; then
  [ -z "$runtime_agent" ] || die "both Codex and Claude runtime markers are set"
  runtime_agent="claude"
fi

case "$lane_agent" in
  ""|codex|claude) ;;
  *) die "invalid agent in $repo_root/.dholbeat-agent" ;;
esac

# A human-triggered cross-reviewer may inspect the author's worktree. Runtime
# identity therefore wins; the worktree marker is only a non-agent fallback.
agent="${runtime_agent:-$lane_agent}"
if [ -z "$agent" ]; then
  case "${GITHUB_AGENT_IDENTITY:-}" in
    codex|claude) agent="$GITHUB_AGENT_IDENTITY" ;;
    "") die "cannot identify agent; run inside an agent session or agent worktree" ;;
    *) die "GITHUB_AGENT_IDENTITY must be 'codex' or 'claude'" ;;
  esac
fi

case "${1:-}" in
  --whoami)
    printf '%s\n' "$agent"
    exit 0
    ;;
  --expected-login)
    config_file="${GITHUB_AGENT_APP_CONFIG_DIR:-$HOME/.config/github-agent-apps}/${agent}.env"
    [ -f "$config_file" ] || die "missing personal GitHub App profile: $config_file"
    # shellcheck disable=SC1090
    source "$config_file"
    [ -n "${GITHUB_APP_SLUG:-}" ] || die "GITHUB_APP_SLUG is missing in $config_file"
    printf '%s[bot]\n' "$GITHUB_APP_SLUG"
    exit 0
    ;;
  "") ;;
  *) die "usage: scripts/github-app-token.sh [--whoami|--expected-login]" ;;
esac

for command_name in curl jq openssl; do
  require_command "$command_name"
done

config_dir="${GITHUB_AGENT_APP_CONFIG_DIR:-$HOME/.config/github-agent-apps}"
config_file="$config_dir/${agent}.env"
[ -f "$config_file" ] || die "missing personal GitHub App profile: $config_file"

# The profile is a user-owned 0600 shell fragment containing only GITHUB_APP_* values.
# shellcheck disable=SC1090
source "$config_file"

[ -n "${GITHUB_APP_ID:-}" ] || die "GITHUB_APP_ID is missing in $config_file"
[ -n "${GITHUB_APP_OWNER:-}" ] || die "GITHUB_APP_OWNER is missing in $config_file"
[ -n "${GITHUB_APP_PRIVATE_KEY_PATH:-}" ] ||
  die "GITHUB_APP_PRIVATE_KEY_PATH is missing in $config_file"
[ -f "$GITHUB_APP_PRIVATE_KEY_PATH" ] ||
  die "private key file not found: $GITHUB_APP_PRIVATE_KEY_PATH"

base64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

now="$(date +%s)"
issued_at="$((now - 60))"
expires_at="$((now + 540))"
header="$(printf '{"alg":"RS256","typ":"JWT"}' | base64url)"
payload="$(
  printf '{"iat":%s,"exp":%s,"iss":"%s"}' \
    "$issued_at" "$expires_at" "$GITHUB_APP_ID" | base64url
)"
unsigned="$header.$payload"
signature="$(
  printf '%s' "$unsigned" |
    openssl dgst -sha256 -sign "$GITHUB_APP_PRIVATE_KEY_PATH" -binary |
    base64url
)"
jwt="$unsigned.$signature"

installation_id="${GITHUB_APP_INSTALLATION_ID:-}"
if [ -z "$installation_id" ]; then
  installation_id="$(
    curl -fsS --connect-timeout 10 --max-time 30 --retry 2 \
      -H 'Accept: application/vnd.github+json' \
      -H "Authorization: Bearer $jwt" \
      -H 'X-GitHub-Api-Version: 2022-11-28' \
      'https://api.github.com/app/installations?per_page=100' |
      jq -er --arg owner "$GITHUB_APP_OWNER" '
        [
          .[]
          | select((.account.login | ascii_downcase) == ($owner | ascii_downcase))
          | .id
        ]
        | if length == 1 then .[0]
          elif length == 0 then error("App is not installed for configured owner")
          else error("multiple matching installations; set GITHUB_APP_INSTALLATION_ID")
          end
      '
  )"
fi

curl -fsS --connect-timeout 10 --max-time 30 --retry 2 \
  -X POST \
  -H 'Accept: application/vnd.github+json' \
  -H "Authorization: Bearer $jwt" \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "https://api.github.com/app/installations/${installation_id}/access_tokens" |
  jq -er '.token'

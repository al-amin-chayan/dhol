# Personal GitHub Apps for agents

Codex and Claude Code use separate personal GitHub Apps. The Apps are not tied
to Dholbeat: the same two installations can be enabled for any repository owned
by `al-amin-chayan`.

## Local secret layout

Private material is outside every repository:

```text
~/.config/github-agent-apps/       mode 0700
├── codex.env                      mode 0600
├── codex.private-key.pem          mode 0600
├── claude.env                     mode 0600
└── claude.private-key.pem         mode 0600
```

Each profile contains the non-secret App metadata and the path to exactly one
agent's key:

```bash
GITHUB_APP_SLUG=chayan-codex
GITHUB_APP_ID=<numeric App ID>
GITHUB_APP_OWNER=al-amin-chayan
GITHUB_APP_PRIVATE_KEY_PATH=/Users/chayan/.config/github-agent-apps/codex.private-key.pem
```

Use the corresponding Claude values in `claude.env`. The installation ID is
discovered at token-mint time from the configured owner. If an App has more
than one installation for the same owner, add
`GITHUB_APP_INSTALLATION_ID=<numeric installation ID>` to that profile.

Keep a recovery copy of each private key in the password manager. The local
files are working copies and must not be the only recoverable copies.

## Agent isolation

`scripts/github-app-token.sh` detects the current runtime or worktree marker;
it does not accept an agent name. This keeps routine commands from selecting
the other agent's profile.

```bash
scripts/github-app-token.sh --whoami
scripts/github-app-token.sh --expected-login
scripts/github-app-gh api installation/repositories
scripts/github-app-git push https://github.com/OWNER/REPOSITORY.git BRANCH
```

The wrappers mint a new token for every `gh` or authenticated `git` command.
They fail before launching the underlying command if minting fails, clear Git's
inherited credential helpers, and prohibit SSH or implicit named remotes. Never
persist the one-hour token, run `gh auth login`, or call authenticated `gh` or
`git` directly.

## Enable another personal repository

In GitHub, open each App's installation configuration and add the repository
to its selected repositories. Do this for both Apps. No new App, private key,
or local profile is needed. Confirm access with each agent in its own,
human-started session before allowing writes.

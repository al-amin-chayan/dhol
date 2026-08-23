# Runbook — bootstrap `publish-1`

Bootstrap the second VPS as the canonical `publish-1` host: the shared baseline
only, with no application, no provider route, and no social or provider
credential. Those arrive through their own issues.

This runbook starts from a clean checkout. It assumes no prior setup on the
laptop beyond Docker and Git, and no state that is not either committed or held
in the password manager.

> `core-2` is the founder's shorthand for this machine. Its canonical inventory
> and service role is `publish-1`. There is no `core-2` role.

## 0. Boundaries you must not cross

- **The provider purchase is manual and founder-owned.** No command in this
  repository creates, resizes, or destroys a VPSDime service. Issue creation is
  not purchase approval.
- **Never target `core-1`.** Every command below names `--limit publish-1`.
- **No address is ever committed.** `infra/inventories/production/hosts.yml`
  carries identity only; the address is an operator argument, redacted out of
  every artifact.
- **No host key is ever auto-trusted.** You supply a `known_hosts` file built
  from a fingerprint you read out of band.
- **CI never applies.** `release_policy.ci_apply_allowed` is `false` and the
  commands refuse to run when `CI` or `GITHUB_ACTIONS` is set.

## 1. Record the provider facts

Add the second monthly Linux6GB service to the existing VPSDime account, ideally
in a different datacenter from `core-1`, with key-only bootstrap access.

Record in `infra/inventories/production/baseline/publish-1.yml`:

| Field | Meaning |
| --- | --- |
| `provider.vendor`, `provider.plan` | the purchased service |
| `provider.account_boundary` | which account owns it |
| `provider.datacenter` | the chosen region label |
| `provider.purchase_receipt_location` | where the receipt lives — a pointer, never a copy |
| `provider.monthly_cost_usd` | the recurring line item |
| `expected_host.*` | the operating-system image, distribution, architecture, and resource floor the contract asserts before mutating |
| `bootstrap.identity` | the login the provider delivered |
| `bootstrap.address_variable` | the named local override; the address itself stays out of Git |

The purchase receipt is provider-owned. Never copy an invoice, account
identifier, or payment detail into this repository.

## 2. Verify the host key out of band

Read the SSH host key fingerprint from the VPSDime console, not from the first
connection. Then build a `known_hosts` file outside the repository:

```sh
umask 077
ssh-keyscan -t ed25519 <address> >~/.dholbeat/publish-1.known_hosts
ssh-keygen -lf ~/.dholbeat/publish-1.known_hosts
```

Compare the printed fingerprint with the console. **If they differ, stop.** A
mismatch is a man-in-the-middle, not a hiccup.

## 3. Prove the offline contract

```sh
scripts/check
```

This validates the committed `publish-1` baseline against the same contract the
host will be held to — operating system, architecture, resource floor, named
administrator, break-glass method, SSH allowlist, bounded Docker logging, and
the writable-directory catalog — without contacting anything.

## 4. Generate the reviewed plan

A bare host cannot produce a meaningful Ansible check-mode diff: `ufw`, Docker,
and `chrony` are not installed yet, so the probes those roles depend on cannot
run. First contact therefore has its own plan kind.

```sh
scripts/infra-plan \
  --limit publish-1 \
  --stage bootstrap \
  --address <address> \
  --identity-file ~/.dholbeat/publish-1-bootstrap \
  --admin-identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts
```

Two keys are modelled explicitly. `--identity-file` is the provider bootstrap
key, valid only until convergence disables root login. `--admin-identity-file`
authenticates the named administrator whose public key the committed contract
installs; omit it only when one key does both. The second-connection probe
always authenticates as the administrator, so a mismatched administrator key
fails the probe **before** the firewall or SSH hardening closes the current
path.

`--stage bootstrap` connects as the provider bootstrap identity and runs the
read-only preflight: the declared contract validated against the host's **real**
facts, plus the current package, directory, listener, and firewall state. That
is the reviewable delta for a machine that has nothing on it yet.

The plan fails closed. A nonzero run, an unreachable host, a failed task, or a
missing play recap produces no approvable digest, so a repeatable failure can
never reach founder confirmation.

Evidence lands in `.artifacts/infra-plan-publish-1-bootstrap-<commit>/`. Only a
redacted host-key fingerprint receipt is retained; the operational `known_hosts`
lives in a session directory that is removed when the command exits. The command
then asserts that the address appears in no retained file.

Read `plan.yml` before trusting it. A commit not yet reachable from protected
`main` requires `--rehearsal`, is marked as such, and `scripts/infra-apply`
refuses it.

## 5. Cross-review, tag, and authorize

1. Cross-review the plan and the implementation at the exact head. Claude-authored
   work is reviewed by Codex; Codex-authored work is reviewed by Claude Code.
2. Merge to `main`, then create the annotated tag `infra-prod-YYYYMMDD-N` on that
   commit.
3. Write the release document to `.artifacts/releases/<tag>.yml` matching
   `infra/schemas/release.schema.json`, recording `approved_plan_sha256`, the
   toolchain lock digest, `target_roles: [publisher]`, the required backup
   snapshot, and the opposite-family review of that exact commit.

Release documents live under gitignored `.artifacts/`. They are never committed.

## 6. Converge

```sh
scripts/infra-apply \
  --limit publish-1 \
  --stage bootstrap \
  --release infra-prod-YYYYMMDD-N \
  --address <address> \
  --identity-file ~/.dholbeat/publish-1-bootstrap \
  --admin-identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts \
  --approved-plan .artifacts/infra-plan-publish-1-bootstrap-<commit>/plan.yml
```

`--stage` must match the stage the approved plan was generated with. It selects
only the identity used for **first contact** — the provider bootstrap login,
because the named administrator does not exist yet. Both stages converge the
same `infra/playbooks/site.yml`, so the reviewed desired state never differs
between them, and the pre-apply plan regenerated here is byte-comparable with
the one you approved.

Before touching the host the command requires a clean worktree, `HEAD` equal to
the annotated tag's commit, reachability from protected `main`, a passing
release-identity gate, a freshly generated pre-apply plan byte-identical to the
approved plan, and your typed confirmation. Convergence runs `serial: 1` and
stops on the first failure.

The run proves a second administrator connection **before** the firewall or SSH
hardening can close the current path. A failed probe aborts with bootstrap access
and the unapplied firewall intact — that is the interlock working, not a bug.

Convergence disables root login and restricts `AllowUsers` to the named
administrator, and Ansible's in-play identity switch cannot cross a process
boundary. So once `site.yml` succeeds, the command renders a **second, converged
inventory** and proves the administrator can reconnect before relying on that
path. Only then does it re-read `/etc/dholbeat-release` independently, validate
it against the reviewed release, and run `scripts/infra-verify`.

If that reconnect fails, the host is converged but unverified: recover through
the provider console, then re-run the reviewed plan and apply.

## 7. Prove idempotence and closure

The host now has a named administrator, so every later run uses
`--stage converged`, which connects as that administrator and produces a real
check-mode diff.

```sh
scripts/infra-plan --limit publish-1 --stage converged --address <address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts \
  --artifact-suffix second-run

scripts/infra-verify --limit publish-1 --address <address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts \
  --release-tag infra-prod-YYYYMMDD-N --artifact-suffix idempotence
```

The converged plan must report no changed tasks and bind no diff hunks. Because
every `--diff` hunk is bound into `plan.yml`, a host that drifts cannot
reproduce an earlier digest even when the changed task names are identical.

Verification asserts the declared operating system and resources, the exact held
Docker package versions, bounded daemon logging including `log-opts` limits and
Unix-socket-only access, an active default-deny firewall with the declared
allowlist, the attached Docker ingress chain, catalogued directory ownership and
modes, effective key-only SSH, a working second administrator connection, and
that no undeclared protocol/port pair answers on a public address. It also
proves the Docker daemon is reachable only over its declared Unix socket,
rejecting every non-Unix host declaration, any network socket the daemon owns —
including a loopback binding on a nonstandard port, which the public-listener
probe deliberately ignores — and any `docker.socket` unit that activates a TCP
endpoint behind an innocuous-looking `fd://`.

From here on, ordinary changes are: plan with `--stage converged`, review, tag,
apply with `--stage converged`.

## 8. Break-glass

The tested recovery path is the **VPSDime provider console**, recorded in the
committed baseline as `break_glass` and written to `/etc/dholbeat/break-glass.yml`
on the host. Exercise it once, before you need it.

Use the console when the administrator SSH path is unavailable — a rotated source
address outside the allowlist, a firewall mistake, or a broken `sshd` policy. The
console is a keyboard, not a deployment channel: use it to restore reachability,
then re-run the reviewed plan and apply. Never hand-edit desired state on the
host; an emergency edit is drift, and the next convergence will overwrite it.

Provider recovery logins live in the password manager, never in this repository.

## 9. Rollback and recovery

No application state exists on `publish-1` at this stage, so rollback is
deliberately blunt and complete:

1. Reinstall Ubuntu 24.04 from the provider console.
2. Re-verify the new host key fingerprint out of band.
3. Re-run sections 4–7 against the last known-good annotated release.

Because every input is committed or held in the password manager, a reinstall
loses nothing. Retain the provider console access, the purchase receipt pointer,
the resolved package manifest from `.artifacts/`, and the release document needed
to reproduce the previous state.

A Git revert is not a rollback on its own: stateless configuration converges to
the preceding annotated release, but you must still record which release you are
returning to and why.

## 10. What must not exist yet

At the end of this runbook `publish-1` has the shared baseline and nothing else.
There is deliberately no publisher application, no Compose stack, no Cloudflare
tunnel or public route, no R2 or restic credential, and no social provider
connection. Each arrives through its own issue and its own gate.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| `publish-1` VPSDime Linux6GB | $7 before tax and conversion |
| Baseline tooling, plan, apply, verify | $0 |

Combined two-VPS infrastructure is about $14–15 per month including expected R2,
inside the founder's ≤$75 per month growth budget. Any change to this table needs
an explicit founder cost decision.

# Infrastructure entry points

Everything under `infra/` is desired state plus the read-only checks that prove
it. No command here contacts a host unless you name that host explicitly, and no
command mutates production without an annotated release, a matching plan digest,
and interactive founder confirmation.

Run every tool through the pinned controller. A global Ansible, OpenTofu, SOPS,
or Python installation is never used.

## Layout

| Path | Contents |
| --- | --- |
| `ansible.cfg` | Strict host-key checking and the committed `roles_path` |
| `controller/` | The checksum-locked container image every command runs inside |
| `schemas/` | Versioned JSON Schemas for every manifest |
| `inventories/production/hosts.yml` | Non-secret host, service, and public endpoint identities. It deliberately contains **no address**. |
| `inventories/production/group_vars/` | Timezone, release-receipt, override, and release-approval policy |
| `inventories/production/baseline/` | One committed baseline contract per production host |
| `inventories/fixtures/` | Disposable-host and negative fixtures only |
| `services/` | Service, image, domain, route, volume, and backup-adapter registries |
| `secrets/` | SOPS+age ciphertext and the values-free catalog |
| `release/` | Release identity, plan digest, and host receipt contract |
| `playbooks/` | `baseline.yml`, `preflight.yml`, `bootstrap.yml`, `site.yml`, `verify.yml` |
| `roles/` | Shared baseline roles plus the dependency-gated selected `publisher` role |
| `tests/disposable/` | The disposable Ubuntu convergence harness |
| `tests/tooling/` | Fail-closed coverage for the plan, apply, and verify gates |

## Read-only checks

```sh
scripts/check
```

This runs the same order locally and in CI: repository policy, branch policy,
YAML and shell lint, secret scan, schema contracts, the production inventory and
host baseline contracts, SOPS policy, and every test suite. It contacts nothing.

`scripts/publisher-check` is the narrower offline entry point for the selected
Postiz Compose, mapping, persistence, restore-isolation, and activation-blocker
contracts. It uses synthetic render values and never contacts a host/provider.

## Host commands

```sh
scripts/infra-plan   --limit <host> --stage bootstrap|converged --address <ip> \
                     --identity-file <key> --known-hosts-file <known_hosts>
scripts/infra-apply  --limit <host> --stage bootstrap|converged --release <tag> \
                     --address <ip> --identity-file <key> \
                     --known-hosts-file <known_hosts> \
                     --approved-plan .artifacts/<plan>/plan.yml
scripts/infra-verify --limit <host> --address <ip> --identity-file <key> \
                     --known-hosts-file <known_hosts>
scripts/wireguard-peer-config --peer-id <id> --address <10.99.0.2/32> \
                     --subnet <10.99.0.0/24> --output <path outside the repo>
```

`wireguard-peer-config` writes one administrative peer's private half once,
outside the checkout, and prints only the public key to commit. Move the file
into the password manager and delete the local copy; that is the same custody
rule the age keys and provider recovery logins already follow.

There is no OpenTofu plan adapter yet, so committed declarations under
`infra/tofu` make `scripts/infra-plan` fail closed rather than accept an
operator-supplied file as an external-state delta. That adapter is WP-06.

`--stage` selects only the identity used for first contact, never the desired
state. `bootstrap` connects as the provider login on a host whose named
administrator does not exist yet and plans the read-only preflight, because a
bare host cannot produce a meaningful check-mode diff. `converged` connects as
that administrator and plans a real check/diff whose every hunk is bound into
the plan document. Both apply the same `playbooks/site.yml`.

A plan fails closed: a nonzero run, an unreachable host, a failed task, or a
missing play recap yields no approvable digest.

`--address` is the local override described in
`inventories/production/group_vars/all.yml`. It is supplied on the command line,
never committed, and redacted out of every artifact.

`--known-hosts-file` must already contain the verified host key. No command here
trusts a new key, and `scripts/controller exec-ssh` refuses an empty or symlinked
known-hosts file. Operational host-key material lives in a session directory that
is removed on exit; only a redacted fingerprint receipt is retained, and each
command asserts the address appears in no retained evidence file.

`--identity-file` is the provider bootstrap key; `--admin-identity-file` is the
named administrator's key when it differs. First contact uses the bootstrap key,
every later connection uses the administrator key, and the second-connection
probe always authenticates as the administrator. After convergence hardens SSH,
`scripts/infra-apply` renders a second converged inventory and proves the
administrator can reconnect before relying on that path.

Both identity paths must resolve outside the repository. The check dereferences
symlinked parents and relative paths, so neither `.artifacts/id_target` nor a
symlinked directory can smuggle private key material into the checkout.

Generated plans, receipts, rendered inventories, and transcripts live under
gitignored `.artifacts/`. They are evidence, never repository inputs.

## Bootstrapping a new host

See `docs/runbooks/publish-1-bootstrap.md` for the full sequence, including the
provider-owned purchase boundary, the break-glass path, and rollback.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| Plan, apply, and verify tooling | $0 |

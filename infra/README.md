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
| `playbooks/` | `baseline.yml`, `bootstrap.yml`, `site.yml`, `verify.yml` |
| `roles/` | `base`, `docker`, `firewall`, `release_receipt` |
| `tests/disposable/` | The disposable Ubuntu convergence harness |
| `tests/tooling/` | Fail-closed coverage for the plan, apply, and verify gates |

## Read-only checks

```sh
scripts/check
```

This runs the same order locally and in CI: repository policy, branch policy,
YAML and shell lint, secret scan, schema contracts, the production inventory and
host baseline contracts, SOPS policy, and every test suite. It contacts nothing.

## Host commands

```sh
scripts/infra-plan   --limit <host> --address <ip> --identity-file <key> \
                     --known-hosts-file <known_hosts>
scripts/infra-apply  --limit <host> --release <tag> --address <ip> \
                     --identity-file <key> --known-hosts-file <known_hosts> \
                     --approved-plan .artifacts/<plan>/plan.yml
scripts/infra-verify --limit <host> --address <ip> --identity-file <key> \
                     --known-hosts-file <known_hosts>
```

`--address` is the local override described in
`inventories/production/group_vars/all.yml`. It is supplied on the command line,
never committed, and redacted out of every artifact.

`--known-hosts-file` must already contain the verified host key. No command here
trusts a new key, and `scripts/controller exec-ssh` refuses an empty or symlinked
known-hosts file.

Generated plans, receipts, rendered inventories, and transcripts live under
gitignored `.artifacts/`. They are evidence, never repository inputs.

## Bootstrapping a new host

See `docs/runbooks/publish-1-bootstrap.md` for the full sequence, including the
provider-owned purchase boundary, the break-glass path, and rollback.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| Plan, apply, and verify tooling | $0 |

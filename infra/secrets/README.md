# SOPS secret boundary

Only values-only SOPS+age ciphertext named `*.sops.yml` may live below this
directory. `.sops.yaml` is the sole production creation rule and must contain
the founder and break-glass public recipients confirmed out of band. Private
age keys, SSH keys, provider recovery logins, and the source-escrow recovery
root remain in the password manager.

No production ciphertext is required merely to declare a catalog entry. Create
one only when the real value and both approved recipients are available; never
seed a production path with example or throwaway ciphertext. Test ciphertext is
created from ephemeral in-memory keys under temporary directories and is never
committed.

## Recovery-account checklist

Before the first production ciphertext or apply, the founder verifies that:

- the `dholbeat-sops-root` record contains both private age keys, names their
  independent custodians, and can derive the two public recipients in
  `.sops.yaml`;
- each catalogued `recovery_account.id` exists in the password manager, has a
  current owner and recovery login, and contains no dependency on this Git
  checkout;
- a second device or custodian can retrieve the break-glass key without the
  founder's laptop;
- provider recovery logins are distinct from runtime tokens; and
- a redacted check records only account IDs, recipient fingerprints, date, and
  verifier—never a login, private key, token, or decrypted value.

## Encrypt and validate one set

Prepare the plaintext document only in an editor/process that can pipe directly
to SOPS; do not save it in the repository or `.artifacts/`. Its decrypted shape
is:

```yaml
schema_version: 1
secret_set_id: core
owner_project_id: platform
values:
  catalog-secret-id: value
```

Encrypt to the final `infra/secrets/<set>.sops.yml` path so SOPS selects the
reviewed creation rule. Then run `scripts/check`. At apply time, the validator
decrypts one selected file to process memory, checks its MAC/schema/catalog
keys, and discards the object. It never writes a decrypted workspace copy or
prints a value.

Rendering follows the catalog exactly: select only the values for one target
file/service, render a root-owned mode `0600` file with Ansible `no_log: true`
and `diff: false`, and never copy the complete decrypted set to a host.

## Recipient or private-key leak

Re-encryption is not recovery: old Git ciphertext remains decryptable. Run the
rotation planner in dry-run mode, replace the leaked recipient, rotate every
underlying value in every affected historical SOPS file, revoke the old
provider/runtime values, encrypt fresh values to both current recipients, and
verify each service independently before committing. The planner emits only
secret IDs and paths.

```sh
scripts/controller exec python infra/sops/rotation_plan.py \
  --root /workspace --leaked-recipient age1PUBLIC_RECIPIENT
```

If the Paperclip parity key is affected, rotate it and every service secret
represented by historical parity HMACs before accepting a new baseline.

## Paperclip parity key

Create a new high-entropy controller-only key, rotate every represented service
secret, re-encrypt `core.sops.yml`, and recompute the reviewed baseline. Never
render the parity key to a host or emit an unkeyed value digest.

## n8n encryption key

Treat replacement as an application migration: back up and restore-test n8n,
re-encrypt or recreate credentials through the pinned-version procedure, verify
inactive workflows, then revoke the old key only after rollback evidence is
recorded.

## n8n drift-watchdog key

Create new, verify its read-only owner probe and targeted deactivation in the
inactive fixture, then revoke old. Render it only to
`/etc/dholbeat/n8n-consumer-drift.env`; never attach it to a workflow credential
or Hermes environment.

## Cloudflare tunnel token

Create and verify the new token for one named host tunnel, update only that
host's scoped SOPS set, converge and probe the tunnel, then revoke the old
token. A core token must never authenticate the publisher tunnel or vice versa.

## Restic credentials

Create new credentials for one host repository, prove snapshot and disposable
restore access, update only that host, and revoke old after the rollback window.
The source-escrow recovery root remains a separate password-manager root.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| SOPS, age, schemas, and validation | $0 |

This package adds no service, storage, CI tier, or provider call.

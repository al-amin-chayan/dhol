# SOPS secret boundary

Only values-only SOPS+age ciphertext named `*.sops.yml` may live below this
directory. `.sops.yaml` is the sole production creation rule and must contain
the founder and break-glass public recipients confirmed out of band. The
password manager is authoritative for private age keys, SSH keys, provider
recovery logins, and the source-escrow recovery root. A mode `0600` operator
copy of each age key may live under `~/.config/dholbeat/age/`, matching the
PoriPati and w3exam layout, but it must never be the only copy.

No production ciphertext is required merely to declare a provider-issued
catalog entry. Create one only when the real value and both approved recipients
are available; never seed a production path with an invented provider secret.
`canary.sops.yml` is an intentionally random controller-only proof that both
recipients and the SOPS MAC work. Test ciphertext is created from ephemeral
in-memory keys under temporary directories and is never committed.

The committed public-recipient comments in `.sops.yaml` record SHA-256 over the
exact age recipient string. Reproduce one without exposing its private key:

```sh
age-keygen -y ~/.config/dholbeat/age/founder.age | tr -d '\n' | shasum -a 256
```

## Recovery-account checklist

Before the first provider-issued production ciphertext or apply, the founder
verifies that:

- the `dholbeat-sops-root` record contains both private age keys, records their
  founder and break-glass roles, and can derive the two public recipients in
  `.sops.yaml`;
- each catalogued `recovery_account.id` exists in the password manager, has a
  current owner and recovery login, and contains no dependency on this Git
  checkout;
- provider recovery logins are distinct from runtime tokens; and
- a redacted check records only account IDs, recipient fingerprints, date, and
  verifier—never a login, private key, token, or decrypted value.

On 2026-08-17 the founder accepted a byte-identical NordPass
download-and-restore round trip for both keys as satisfying the initial canary
recovery gate. On 2026-09-13 the founder removed the second-device validation
requirement because no second device is available, superseding that deferred gate.
This is a policy waiver, not a successful drill. Password-manager escrow of both
private keys and provider recovery logins, distinct-recipient checks and independent
SOPS MAC/decryption verification remain mandatory before secret creation or apply.
See README §9/§10 for the recorded decision and shared-recipient recovery risk.

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

Validate the committed canary independently with each local operator key:

```sh
SOPS_AGE_KEY_FILE=~/.config/dholbeat/age/founder.age \
  python infra/sops/validate.py --root . --decrypt infra/secrets/canary.sops.yml
SOPS_AGE_KEY_FILE=~/.config/dholbeat/age/break-glass.age \
  python infra/sops/validate.py --root . --decrypt infra/secrets/canary.sops.yml
```

Rendering follows the catalog exactly: select only the values for one target
file/service, render a root-owned mode `0600` file with Ansible `no_log: true`
and `diff: false`, and never copy the complete decrypted set to a host.

## Recipient or private-key leak

Re-encryption is not recovery: old Git ciphertext remains decryptable. Run the
rotation planner in dry-run mode, replace the leaked recipient, rotate every
underlying value in every affected historical SOPS file, revoke the old
provider/runtime values, encrypt fresh values to both current recipients, and
verify each service independently before committing. The planner emits only
secret IDs and paths. Its output declares `scope: current-working-tree` and
`historical_ciphertext_review_required: true`: it cannot prove that a retired
set is absent from Git history. Before rotating, enumerate historical SOPS
paths and manually inspect any renamed or deleted set plus its catalog version;
rotate every provider value that historical ciphertext represented.

```sh
git log --all --format= --name-only -- \
  ':(glob)infra/secrets/**/*.sops.yml' | sort -u
```

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

## Publisher runtime credentials

Follow the full [publisher credential rotation
runbook](../../docs/runbooks/publisher-operations.md#credential-rotation). Keep
the publisher frozen and rotate one JWT, database/cache, or public-media R2
boundary at a time from a fresh restore-tested backup. Update only the matching
catalog value in the complete `publisher.sops.yml` (JWT/database/cache) or
`publisher-media.sops.yml` (public media only) set, apply the reviewed
exact-host plan, verify its declared consumers, then revoke the old value. A
recipient private-key leak rotates every underlying value recoverable from
historical ciphertext; re-encryption alone is not recovery.

## OpenTofu state key

The Cloudflare state passphrase is a generated controller-only recovery root in
`cloudflare.sops.yml`, never a host credential or a Terraform output. Both age
recipients must decrypt and verify its SOPS MAC before remote-state bootstrap.
An identical ciphertext copy is stored in the private recovery bucket. This
protects against losing the git copy, but both copies depend on the same two age
recipients and do not protect against losing both private keys. The founder
explicitly removed the second-device drill requirement and authorized retaining
this generated state key on 2026-09-13 after that risk was explained. If all
recipient keys are lost, the seven control-plane resources contain no unique
application data: reconstruct state by
reviewing new recipients and empty replacement backend coordinates, then
re-importing the exact IDs in `infra/tofu/cloudflare/adoption.json`, following the
immutable-bootstrap and import-only guards. Do not overwrite an existing primary
state. This fallback applies to Cloudflare infrastructure state; service-specific
credential rotation and backup/restore requirements still apply to other secrets.
Use the [control-plane recovery procedure](../tofu/cloudflare/README.md#recovery-and-rotation)
before replacing the key: preserve the encrypted original state and original
key, prepare a separately recoverable replacement key, migrate in the bounded
controller, and verify a clean-clone no-change plan before retiring the old key.
Recipient compromise also requires rotating every historically exposed
provider/runtime credential; merely encrypting the same key again is insufficient.

## Machine-route credentials

WP-06A declared these inputs without encrypting or installing production values.
On 2026-09-14 the dedicated non-expiring Access service credential was issued
and the existing publisher tunnel token was recovered without rotation; both
now have complete committed SOPS sets under the two approved recipients.
The independent publisher application API key and Telegram webhook secret are
still separate pending inputs. Password-manager uploads of the Access and tunnel
recovery files have completed, but byte-identical retrieval is not yet verified.
Before promotion, verify the password-manager recovery records
and both approved recipients under the current recovery-account checklist. Issue a
dedicated n8n Cloudflare Service Auth token, restricted by an Access application to `publish.chayan.me/api/public/*`, and pair it with the independent
publisher application API key. Never admit `any_valid_service_token` or a whole-host
machine bypass. Rotate both credentials after exposure, converge their scoped core-only
secret file, verify the allowed public API and denied UI/wrong-token paths, then revoke
the old pair. The Telegram secret belongs only in the core webhook proxy file; verify
missing/invalid headers are rejected before n8n sees a request. Keep the previous
credential active only during the bounded rotation window.

## Backup bucket credentials

On 2026-09-14 four non-expiring bucket-scoped R2 pairs were issued for core
backups, publisher backups, public media and independent source escrow. Their
provider-issued values and the three generated restic passwords are committed
in six complete runtime SOPS sets (including Access and tunnel), with independent
MAC recovery verified under both approved age recipients. Password-manager
escrow of these four storage sets and the independent source-root configuration
is still pending; no production backup acceptance is claimed.
The issuer stores the R2 token ID as the S3 access key and SHA-256 of the raw
API token value as the S3 secret access key; it deliberately does not escrow
the raw API token value. Recover the stored S3 pair or issue a replacement;
Cloudflare cannot redisplay the original one-time token value. The generated
restic password is a separate recovery root: replacing an R2 key cannot recover
an existing encrypted repository if that password is lost.
Each restic principal receives only its own private bucket pair;
public-media credentials cannot read either backup bucket. After an exposure, issue a
replacement restricted pair, verify password-manager recovery records and both
approved recipients, encrypt under that host's SOPS set, verify a disposable backup
and restore, converge the host-only file, and revoke the previous pair. Keep restic as the completed-object retention authority; a
bucket lifecycle must never expire restic chunks or snapshots.

After saving all required recovery files in the password manager, download them
to a private temporary directory and verify byte-identical retrieval before
deleting any unverified recovery copy. Then delete the operator plaintext JSON
exports, the temporary source-root `.env`, verification downloads and any
generated plaintext residue under `.artifacts/cloudflare`; inspect temporary
editor copies too. Keep committed SOPS ciphertext. Do not delete unrelated age
keys or existing provider/operator inputs as part of this cleanup. When a later
operation needs plaintext, re-export it temporarily from the password manager,
use mode `0600` outside Git, and delete that temporary copy after use. Record
cleanup with file categories and verification status, never secret contents.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| SOPS, age, schemas, and validation | $0 |

This package adds no service, storage, CI tier, or provider call.

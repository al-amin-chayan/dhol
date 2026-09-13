# Cloudflare control-plane adoption and recovery

WP-06A imports the seven existing DNS/tunnel/Access resources in `adoption.json`
with Cloudflare provider **5.24.0** and OpenTofu **1.12.5**. The initial import and
its follow-up no-change plan succeeded on 2026-09-13. Existing Cloudflare objects,
connector configuration and hosts were preserved. The two new private R2 backend
roots were provisioned under the founder's full-implementation authorization.
See [the author evidence](evidence-2026-09-13.md).

## Source and boundaries

`bootstrap.yml` pins the account, zone, independent backend bucket IDs and exact
production key. These immutable roots are owned by the bootstrap procedure,
not by the state they hold. Deleting/replacing a pinned root is refused.
`adoption.json` independently pins each resource ID and provider import argument.
`resources.tf` derives hostnames, tunnel identities/configuration sources and
core ingress from `routes.yml`. Every adopted resource has `prevent_destroy`.
No other product's bucket, tunnel or Access app is adopted. There was no existing
Dholbeat private bucket: newly provisioned backend roots are private, while
future restic/private-backup and public-media buckets remain planned declarations.

`routes.yml` is the edge manifest, including planned infrastructure endpoints
already admitted by the host inventory. It does not invent deployed entries in
the runtime service registry. Human administration requires founder-only Access;
Telegram has only the `/webhook/*` machine exception, POST, a verifying loopback
proxy and a bounded rate limit. Publisher machine credentials belong only to
n8n and only to `publish.chayan.me/api/public/*`, plus the publisher's independent
application key. Each host has a distinct tunnel/token reference and private
backup pair. Public media has a separate publisher pair and seven-day expiry;
restic remains the private-backup retention authority.

`team` is adopted. `n8n` and `hooks` are planned. `publish` currently exists
without Access and is marked `existing-unprotected`. Its security overlay and
future resources belong to the subsequent WP-06C mutation/promotion lane;
WP-06A installs nothing. The down core connector is an availability issue,
not repaired by control-plane import. These are explicit promotion gates.

## Operator inputs and commands

Build the checksum-locked controller with `scripts/controller build`. Operator
input files must be regular, mode 0600, outside every git checkout and outside
GitHub identity directories. Both founder and break-glass age key exports are
required; SOPS decrypts and verifies both recipients in memory. The existing
password-manager recovery record remains the root authority. The outstanding
physical second-device retrieval gate still applies before encrypting future
provider-issued production credentials; local recipient checks do not replace it.

The private credential input contains only:

```text
CF_ACCOUNT_ID=<account ID from bootstrap.yml>
CLOUDFLARE_API_TOKEN=<account/zone scoped operator token>
CLOUDFLARE_R2_BOOTSTRAP_TOKEN=<password-manager R2 administrative root>
```

The provider token needs DNS/Zone, cloudflared, Access Apps/Policies and Registrar
permissions for this account/zone. Read permissions suffice after adoption;
the founder-approved one-day bootstrap token had write permissions. The R2
parent is consumed only by the bootstrap delegator. OpenTofu receives one-hour
JWT S3 credentials restricted to its bucket and prefix. Provider tokens never
reach hosts, process arguments, plans, receipts or committed ciphertext.

```sh
scripts/cloudflare bootstrap \
  --credentials ~/.config/dholbeat/cloudflare/operator.env \
  --founder-key ~/.config/dholbeat/age/founder.age \
  --break-glass-key ~/.config/dholbeat/age/break-glass.age \
  --confirm cloudflare-control-plane
```

Use the same arguments with `validate`, `adopt`, `plan`, `verify`, `probe`,
`recovery-drill`, `snapshot` or `clean-drills`. CI cannot invoke this entry point.
The source and all inputs mount read-only. Provider binaries execute only from
a bounded executable tmpfs cache; temporary backend metadata, encrypted plans
and working directories disappear with the container. No local state becomes
authoritative. Evidence filenames are finite and overwritten under ignored
`.artifacts/cloudflare/`; evidence contains IDs, booleans and hashes only.

`adopt` is the only production apply entry point. It constructs import blocks,
plans using the locked provider, checks the complete independent address/ID
inventory, and applies that exact encrypted binary only if all resource actions
are no-op. It then replans without imports and requires exit 0. Resource drift,
unknown/deferred actions, output changes, failed checks, extra providers and
source/state races fail closed. An idempotent repeat cannot mutate a resource.
`plan` always uses a new workspace, validates the actual provider plan and emits
a fresh receipt. There is no generic resource apply/destroy command.

`infra-plan` now runs this real external plan immediately before rendering its
host approval document. Configure `DHOLBEAT_CLOUDFLARE_CREDENTIAL_FILE`,
`SOPS_AGE_KEY_FILE` and `DHOLBEAT_BREAK_GLASS_KEY_FILE` as local file paths, or use
the defaults shown above. Its receipt must bind the entire current package,
secret catalog/ciphertext, domains, host inventory, versions and unchanged
remote state, and must be no older than five minutes. Unadapted packages fail
closed. `infra-apply` already replans and compares the stable external-state
binding; encrypted-plan randomness does not invalidate an unchanged approval.

## Two-stage bootstrap

1. Before first provisioning in a new approved account, review a bootstrap
   descriptor with `authority: initial-bootstrap` and both bucket IDs null.
   `bootstrap` may create only the two exact Dholbeat root names, checks their
   private/no-completed-object-expiry posture, and emits candidate IDs. It does
   not initialize state. Repeating this stage validates/resumes its own roots.
2. Commit the returned IDs with `authority: immutable-bootstrap`, which is the
   current descriptor. Validate both roots, independently recover the SOPS
   state passphrase, and initialize its encrypted recovery copy with a
   conditional create. A different recovery ciphertext is never overwritten.
   Run the disposable locking/recovery drill before `adopt` initializes state.

Missing pinned roots stop the operator; do not reset IDs to conceal their
loss. Root replacement needs a separately reviewed recovery descriptor and
founder authorization. Default multipart-upload abortion is allowed, but
r2.dev/custom-domain public exposure and completed-object lifecycle expiry are
rejected. No native S3 versioning is assumed.

## Routes and probes

```sh
scripts/controller exec python infra/tofu/cloudflare/edge.py --host core-1
scripts/controller exec python infra/tofu/cloudflare/edge.py --host core-1 --include-planned
scripts/controller exec python infra/tofu/cloudflare/edge.py --host publish-1
```

Every manifest is validated completely before rendering either host. Every
output ends with `http_status:404`. The older `control_plane.py render-ingress`
is a strict adapter for the deployed version-1 service registry; it supports
only human whole-host ingress. New/future routes use `edge.py`.

`verify` performs live policy/DNS/registrar checks and independent non-recursive
DNS queries directly to both recorded `.me` parent servers, then proves the
existing `team` unauthenticated Access denial. It reports planned/unprotected
routes separately. `probe` executes read-only GET probes for adopted routes:
anonymous, wrong-founder, alternate Host and out-of-path denial; a provided
scoped founder session also exercises the positive route. Optional private
input keys are `FOUNDER_ACCESS_JWT_PAPERCLIP_ADMIN`,
`FOUNDER_ACCESS_JWT_N8N_ADMIN`, `FOUNDER_ACCESS_JWT_PUBLISHER_ADMIN_API`,
`N8N_ACCESS_CLIENT_ID`, `N8N_ACCESS_CLIENT_SECRET`, `PUBLISHER_API_KEY`,
`PROBE_CORE_1_IP` and `PROBE_PUBLISH_1_IP`. Direct-IP probes use only an explicit
public host IP and the manifest's origin port. Credentials are sent only to the
canonical HTTPS route, never to an alternate Host or direct IP; redirects are
not followed. Missing sessions/IPs and unpromoted routes are reported as
required inputs, never successful positive probes.

The complete fixture matrix includes founder/service-token positive and wrong
identity cases, unauthenticated denial, methods, paths, direct-IP and alternate
DNS. A down origin, generic application login or 5xx cannot establish Access
denial. The real local HTTP proxy tests cover valid forwarding, invalid/missing
or duplicated headers, ambiguous framing, encoded/traversal paths, JSON limits,
rate limits, oversized responses and upstream redirects. Live POST probes are
excluded to avoid invoking a production workflow. Before later promotion,
repeat the full matrix with disposable workflow fixtures and scoped identities,
verify application authentication and host listener/firewall contracts, and
complete publisher Access. Nothing may publish without Telegram approval.

## Recovery and rotation

State and saved plans use enforced PBKDF2/AES-GCM client encryption with no
plaintext fallback. Native OpenTofu conditional `.tflock` locking was tested
against R2, including a second writer, wrong unlock identity, correct unlock,
wrong encryption key and independent restoration from a clean workspace.
`recovery-drill` uses only a built-in-provider disposable key; it cleans its own
objects on failure/success and refuses an inventory of 20 leftover objects.
`clean-drills` never touches production state and refuses unknown/locked objects;
it decrypts and verifies the exact disposable built-in resource before deletion.

`snapshot` verifies the production envelope, conditionally uploads to the
independent recovery bucket and reads it back before pruning. Each state object
is bounded to 4 MiB; each snapshot prefix retains at most 20 entries. Failed
candidates are removed without deleting previous snapshots or credential roots.
Both primary and independent roots are private. Git also retains the SOPS
passphrase ciphertext, and both age private keys remain in the password manager.

After primary-object loss, stop writers and choose a reviewed verified snapshot.
Create a **non-secret** recovery request with `schema_version: 1`, `snapshot_key`,
`sha256`, `backend_bucket: dholbeat-tfstate`,
`backend_key: cloudflare/production.tfstate`, and `expected_primary_absent: true`.
Run `scripts/cloudflare restore` with the standard private-input arguments plus
`--recovery-request <reviewed request file>`. Restore refuses an existing primary,
validates the exact snapshot digest, decrypts from the independent backend into
memory and checks all provider IDs before conditionally creating the primary.
Run a fresh `plan` afterward; drift requires a separate repair review. Never
`destroy`, migrate through plaintext/local authoritative state, or remove an
unidentified lock. A stale native lock may be unlocked only after proving the
writer has stopped and matching its exact lock identity.

Rotation is an explicit separate operation: retain the old recoverable key and
verified independent snapshot, test a migration with both old/new encryption
methods against a disposable encrypted state, migrate the locked state with
reviewed provider-no-change code, verify clean-clone recovery under both age
recipients, and replace the independent credential root only after read-back.
Update the catalog and committed SOPS ciphertext; revoke/retire the old root
only after the retention/recovery window. This package does not offer an
unguarded passphrase overwrite. Reverting repository code never deletes adopted
provider objects or remote state; recover the matching encrypted snapshot if
state itself needs rollback.

## Verification and cost

```sh
scripts/controller exec pytest -q -p no:cacheprovider infra/tests/tooling/test_cloudflare_*.py
scripts/check
```

Canonical checks are offline; they cannot reach providers. Live operator receipts
are separate from fixture proofs and never authorize host/provider mutations.

| Component | Monthly change |
| --- | ---: |
| OpenTofu/provider/controller/probe software | $0 |
| Two private R2 roots and bounded encrypted snapshots | Within existing $0–1 R2 baseline |
| Planned public media/private backup declarations | $0 provisioned by this lane |

Official references: [provider 5.24.0 source](https://github.com/cloudflare/terraform-provider-cloudflare/tree/v5.24.0),
[OpenTofu encryption](https://opentofu.org/docs/v1.12/language/state/encryption/),
[S3 native lockfile](https://opentofu.org/docs/language/settings/backends/s3/),
[R2 temporary credentials](https://developers.cloudflare.com/r2/examples/authenticate-r2-temp-credentials/),
[R2 S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/).

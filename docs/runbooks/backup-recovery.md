# Publisher backups and independent source recovery

WP-07 is opt-in on `publish-1`. It does not replace any `core-1` legacy backup,
cron job, repository, or retention policy. Code tests are not production recovery
evidence. Keep #15 open until the receipts below exist; #17 additionally needs
the selected publisher's deployment, application fixture, and seven-day canary.

## Reviewed installation and first recovery

1. Complete [the boundary rollout](publisher-boundaries.md). Put the scoped
   `publisher-backups`, `publisher-media`, and `source-escrow` ciphertext files in
   `infra/secrets/` under `.sops.yaml`; verify MAC recovery with both age roots.
   Export the independent source roots to the password manager before relying
   on any uploaded bundle. No plaintext secret belongs in a plan or receipt.
2. Promote the cross-reviewed implementation through `develop` to `main` and
   annotate its merge commit `infra-prod-YYYYMMDD-N`. Production helpers verify
   the merged promotion PR, its opposite-model exact-head approval, and equal
   source/merge trees; they do not treat a local tag as review evidence.
3. Set `restic_enabled: true` in a reviewed inventory change, initially keeping
   `restic_timer_enabled: false`. Set the publisher adapter only when the
   corresponding application adoption is reviewed. Generate `scripts/infra-plan
   --limit publish-1`, inspect its host-only diff and capacity, and obtain the
   founder's exact-plan confirmation before `scripts/infra-apply`. Use the
   existing release/known-host/SSH options from `infra-plan --help`.
4. Initialize the proven-absent `/state` repository using `scripts/infra-backup
   init --limit publish-1 --address <WireGuard-IP> --identity-file <private-key>
   --known-hosts-file <pin-file> --release <tag> --review-pr <promotion-PR>`.
   Initialization refuses an existing unpinned repository; preserve the returned
   repository identity with its password-manager root.
5. Run `scripts/infra-backup backup` and `scripts/infra-backup status` with the
   same host/address/identity/pin options. Save the full snapshot ID and redacted
   duration/size receipt. Run `scripts/infra-backup restore-disposable --snapshot
   <64-hex-ID> --name dholbeat-restore-wp07 --loopback-port 5200` with those options.
   The restore always removes its owned disposable directory and the adapter
   removes its disposable containers/volumes. A receipt with
   `application_restore_verified: false` proves only foundation/config recovery.
6. For the real application drill, take a fresh backup with
   `--visibility-control-post-id <scheduled-fixture-ID>`. Restore that full
   snapshot ID and require `visibility_control_verified: true` as well as
   `application_restore_verified: true`. A backup without a control can prove
   database/config restoration but does not prove the exact Visibility query.
   Record real publisher SQL/Redis/Temporal/Elasticsearch dump recovery and the
   application's disposable fixture checks. Record observed RPO (age of the
   recovered successful snapshot), measured RTO, repository ID, cleanup,
   retained config/secret fingerprints, and the tested release. Never record
   dumps, `.env` values, keys, or service-token headers.
7. Only after successful real recovery, install the reviewed
   `/etc/dholbeat/receipts/wp07-publish1.yml` (`gate: wp07-publish1`,
   `host_id: publish-1`, `verified: true`, and full
   `reviewed_head`) and enable timers through another exact host plan. Ansible
   refuses timer activation without that receipt. Keep evidence truthful;
   local fixture success is not authorization to synthesize a live receipt.

## Bounds and failure handling

Application dumps use a physically preallocated fixed 2 GiB ext4 image mounted through FUSE at
`/var/lib/dholbeat/restic/application`, shared with the publisher adapter and
Elasticsearch's `/snapshots` mount. Installation requires at least 10 GiB free
before provisioning the image (2 GiB reserve plus 8 GiB update headroom).
The LXC host must expose an accessible `/dev/fuse`; no loop device is required.
The root-owned `mount.dholbeat-fuse2fs` helper accepts only this image and
mountpoint and enforces `nosuid,nodev,noexec,default_permissions`. Its
`allow_other` flag permits Elasticsearch UID 1000 to use the container bind
mount while the host's parent backup directory remains root-only. This is
disk-backed scratch, not a RAM-backed filesystem. Scratch is disposable;
the image is never reformatted on retry, and a failed mount stops deployment
and backups rather than allowing writes into an unbounded directory.
Retained config/receipts have a separate 16 MiB quota. Raw database volumes,
Elasticsearch live data, caches, generated media, and logs are excluded. SQL
dumps, Redis persistence and the offline Elasticsearch snapshot are produced by
the existing state adapter while publisher workers are stopped; its cleanup
restarts workers even on failure. Formatting disables discard so the image's
reserved blocks are retained. The common publisher lock excludes concurrent
application mutation; a separate adapter lock prevents nested-lock deadlock.

The root oneshot has 256 MiB RAM, 50% CPU, a two-hour timeout, private scratch,
and a root-only credential environment. Tar data streams directly into restic;
no second plaintext upload archive remains on disk. Restore downloads and
expanded member bytes are bounded to 2 GiB and reject links, special files,
duplicate members and traversal. Only a new named disposable target and
reserved loopback port are accepted; production replacement is not a command.
Restore reserves space for both download and extraction (4 GiB worst case),
plus the 8 GiB host reserve, before starting. The adapter separately checks
capacity for its disposable data volumes. Do not run a disposable publisher alongside production if its capacity plan
does not fit: use a disposable recovery host for the live drill.

The daily UTC 03:00 timer retains seven daily and four weekly state snapshots,
grouped by host/tags with a stable `state.tar` path. `forget`, `prune`, then
`check` must all succeed before the success timestamp advances. Source bundles
use a separate repository and explicit retention, so state pruning cannot
remove deployed source. Hourly status fails for a failed attempt, future or
older-than-26-hour success, wrong host, or oversized snapshot. The alert unit
writes an actionable bounded-journal error; Telegram delivery is a later
approval-bot integration, not implemented by this unit.

Ordinary failures remove owned temporary dumps. A killed process, interrupted
filesystem formatting, stale `.new` status file, or nonempty staging stops the
next operation. Inspect the named root-only path and locks, preserve evidence,
then explicitly clear only that interrupted operation. Do not erase or repin a
repository to make a check pass. Rollback stops the two new timers first;
retain repository credentials, identities and snapshots for recovery.

## Independent source root

Source recovery must not need SOPS from the bundle it is trying to download.
Store provider recovery login, source bucket credential, restic password, full
repository URL/ID and snapshot receipts in the password manager. The dedicated
source credential is bucket-scoped to `dholbeat-source-escrow`; `/source` uses a
distinct restic password/identity from either host's `/state` repository. The
source bucket is controller-owned and has no host-file credential target.
R2 bucket scope separates the blast radius: neither host backup credential can
access source escrow, and the source credential cannot access host backups.
Neither backup/source credential is mounted into Postiz; its public-media
credential cannot read any private bucket.

Export a regular mode-0600 file outside every Git checkout containing
`RESTIC_REPOSITORY` (dedicated private source bucket `/source`), `RESTIC_PASSWORD`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
`SOURCE_ESCROW_REPOSITORY_ID`. Set the last field to `new` only for a proven
absent repository. `scripts/repository-bundle init --root-file <export>
--release <tag> --review-pr <promotion-PR>` requires interactive founder
confirmation, pins the new ID atomically in that file, and requires updating
the password-manager copy before use.

`scripts/repository-bundle create --root-file <export> --release <tag>
--review-pr <promotion-PR> --deployed-releases <JSON>` runs on a clean checkout
of that annotated release, reachable from `main`. The JSON names both hosts,
for example `{"core-1": null, "publish-1": "infra-prod-YYYYMMDD-N"}`; null means
the host has not been adopted, not an unknown deployed release. Verify against
actual host release receipts. Git creates a file-size-limited 256 MiB bundle
of `main` plus every annotated production tag, verifies it and uploads only
encrypted restic data. Temporary bundles are deleted on success and failure.
No GitHub credential or clone is installed on a production host.

Retention protects the newest bundle containing every currently deployed tag,
the last two superseded release bundles, and the newest bundle. Missing host
catalog entries, missing deployed-tag coverage or an oversized snapshot catalog
fail before deletion. Bundle coverage tags allow a new bundle to escrow an
older deployed tag even when it had no previous source snapshot.

For a GitHub outage, obtain the root export and full snapshot ID independently,
then run `scripts/repository-bundle recover --root-file <export> --snapshot
<64-hex-ID> --destination .artifacts/source-recovery-<unique-name>`. Download
uses only R2; digest/quota, `git bundle verify`, annotated tag and exact
main/release commit checks use only that restored file. The original clone and
GitHub are not consulted. The recovered disposable clone intentionally remains
for inspection; remove it explicitly afterward. Save the redacted receipt and
measured outage-drill time. Local Git tests exercise this path with the old
clone deleted; production acceptance still requires a real encrypted R2 upload.

Also escrow a `source-recovery-kit.tar.gz` attachment containing
`scripts/lib/source_recovery_bootstrap.py`, `scripts/lib/source_escrow.py`,
`scripts/lib/repository_bundle.py`, and these instructions, with the three
Python files at the archive root. Rebuild it when recovery code changes and
verify its downloaded bytes alongside the independent root. The kit contains
public code only; it must never contain the root export, age keys or a bundle.
On a fresh machine with Python 3.11+, Git and pinned restic 0.19.1, retrieve
the kit, root export and snapshot receipt from the password manager, extract
the kit into a private directory outside Git, chmod the root export 0600,
and run from that directory:

```sh
python3 source_recovery_bootstrap.py --root-file /PRIVATE/source-escrow-root.env \
  --snapshot FULL_SNAPSHOT_ID --destination /PRIVATE/new-recovered-checkout
```

This bootstrap uses installed Git/restic directly, so it requires neither
the original checkout nor its locally built Docker controller. Only the
restored bundle is an allowed Git remote. It verifies repository ID, snapshot
purpose, quotas, bundle digest, annotated release and exact commits before
returning success; temporary downloads are removed on every exit. Keep the
verified release's snapshot ID in the same password-manager recovery record.

Rotate exposed bucket credentials through a separately reviewed scoped issuance
plan, recover with the new credentials, and revoke only the replaced dedicated
credential. Restic password exposure requires replacing/removing compromised
key slots and assessing old snapshot confidentiality; adding a password does
not re-encrypt historic data. Age-key exposure also requires rotating every
represented provider credential, not merely changing recipients.

| Component | Added monthly software cost | Usage bound |
|---|---:|---|
| restic, systemd, Git bundles | $0 | 2 GiB dump scratch; 256 MiB bundle |
| Private R2 state/source | Existing R2 usage pricing | 7 daily/4 weekly state; protected source tags |
| Public R2 media | Existing R2 usage pricing | 7-day lifecycle; 1-day incomplete multipart cleanup |

There is no new paid subscription. These bounds cap local staging and retained
generations; they do not guarantee a fixed provider bill as application data
grows. Check measured R2 storage/operations against README's $10–25/month
platform ceiling before activating additional hosts.

### Reading first-install plan changes

The read-only restic plan reports a changed installation annotation when the
locked binary is absent or differs. That check-only task is included in the
approved plan digest; application instead downloads and installs the locked
artifact. Plan and apply changed-task counts therefore need not match task for
task. Compare the reviewed artifact, source hashes and intended final state,
rather than treating the differing task names as drift.

The WP-07 timer-admission receipt is independently installed before activation.
Its exact-host recovery validation runs during planning and application: a
missing or invalid receipt blocks an activation plan. This is an authorization
precondition, not a postcondition that check mode would need to create.

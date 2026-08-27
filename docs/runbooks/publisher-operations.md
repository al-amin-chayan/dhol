# Postiz deployment, recovery, and safety operations

This runbook owns only the selected Postiz `v2.23.0` adapter. It does not
authorize a production apply, provider connection, social post, or capacity
upgrade. The architecture plan and issue #17 remain authoritative.

## Current blocked boundary

The desired state is committed inactive. Keep `publisher_enabled: false` while
any of these receipts is absent or unverified on `publish-1`:

| Receipt gate | Owning issue | Required outcome |
| --- | --- | --- |
| `wp05d-publish1` | #45 | Host exists, baseline is idempotent, and administration is WireGuard-only. |
| `wp06b-publish1` | #14 | `publish.chayan.me`, founder Access, n8n service-token policy, tunnel, and distinct media/private-backup R2 boundaries pass negative probes. |
| `wp07-publish1` | #15 | Encrypted host backup, source escrow, bounded staging, and disposable restore foundation pass. |

Safe repository checks may run before those gates. No command in this runbook
may synthesize a receipt or use an empty placeholder to bypass one.

## Prepare activation

1. Confirm `docs/decisions/publisher-selection.md` still records Postiz
   `v2.23.0` and the exact image digest in `stack/publisher/postiz/compose.yml`.
2. Run `scripts/publisher-check` and `scripts/check` from a clean checkout.
3. Verify all three dependency receipts contain `host_id: publish-1`,
   `verified: true`, their exact gate ID, and a cross-reviewed 40-character
   `reviewed_head`.
4. Complete the second-device age-key retrieval drill before creating the first
   provider-issued R2 key. Generate the JWT and three database/cache passwords
   locally with at least 32 URL-safe random characters. Never print them.
5. Encrypt the complete `publisher` SOPS set in one process-memory flow. It
   includes every catalog key targeting `infra/secrets/publisher.sops.yml`, not
   merely the six keys added by WP-13. Do not commit a partial or invented set.
6. Fill only the non-secret R2 account ID, bucket name, and public media URL in
   `group_vars/publisher.yml`. Verify the media credential cannot access either
   private restic repository and the bucket has the reviewed expiry lifecycle.
7. Change `publisher_enabled` to `true` and remove only blockers backed by the
   receipts. Prepare an annotated, cross-reviewed release and inspect:

   ```sh
   scripts/infra-plan --limit publish-1 --stage converged \
     --address ADDRESS --identity-file ADMIN_KEY --known-hosts-file KNOWN_HOSTS
   ```

8. Apply only the byte-identical plan after founder confirmation, then run
   `scripts/infra-verify --limit publish-1` and a second no-change plan. All
   provider/social mappings remain fixtures or absent.

The role binds Postiz only to `127.0.0.1:5000`; state services publish no host
ports. WP-06B owns the tunnel route and must continue to prove that direct IP,
alternate DNS, unauthenticated UI, wrong service token, and state-service
origins fail.

## Founder account and registration window

Postiz creates an organization only as a registration side effect. The founder
is the sole owner of this bounded manual action.

1. Confirm no real provider account is connected, the founder Access policy is
   effective, a fresh application-aware backup exists, and an operations alert
   is visible.
2. Record founder confirmation, the reviewed release, intended project ID, and
   a ten-minute end time in a redacted local receipt.
3. Over the WireGuard administration path, recreate only Postiz with a temporary
   process override:

   ```sh
   cd /opt/dholbeat/publisher
   POSTIZ_DISABLE_REGISTRATION=false docker compose up --detach --force-recreate postiz
   ```

4. Through `publish.chayan.me`, register exactly one founder-controlled project
   account. Do not connect a social provider.
5. Close registration immediately by reconciling committed desired state:

   ```sh
   cd CONTROLLER_CHECKOUT
   scripts/infra-apply --limit publish-1 --stage converged --release REVIEWED_TAG \
     --address ADDRESS --identity-file ADMIN_KEY --known-hosts-file KNOWN_HOSTS \
     --approved-plan APPROVED_PLAN
   ```

6. Verify a new unrelated registration is rejected while the existing founder
   login and its organization still work. If the window overruns or close
   verification fails, activate the host kill switch and investigate before
   continuing.

The redacted receipt records only project ID, organization ID, release, start/
end time, and rejection result. It never records an email, password, API key,
session, or OAuth grant.

## Mapping and credentials

Add one data manifest per project only after its organization exists. For this
Postiz adapter, `workspace_id` equals `organization_id`; it is the neutral
mapping interface, not a claim that Postiz exposes a second workspace object.
Every brand account entry has a unique Postiz integration ID, provider-grant
catalog ID, and owner project. `scripts/publisher-check` rejects reuse.

Mint and rotate one Postiz public-API key per organization. Store its value only
in that project's SOPS-scoped secret set and expose it only to the project's n8n
publisher credential. n8n also uses the independently renewable WP-06B Access
service token. Neither credential alone bypasses the other layer. Hermes never
receives either credential.

Connecting a real social account is a later explicit founder-approved canary.
Immediate publish, token refresh, provider duplicate protection, and real
provider failure behavior remain unproved until that canary; do not relabel a
database fixture as provider evidence.

## Kill switch and cancellation

Freeze globally before a suspected duplicate, stale approval, restore, or
unbounded retry can reach a provider:

```sh
sudo dholbeat-publisher-control freeze --reason 'INCIDENT REASON'
sudo dholbeat-publisher-control status
```

The marker is written before Postiz and Temporal stop. Ansible's publisher-only
Docker CLI guard takes the same host lock, rechecks the marker under that lock
immediately before any `compose up`, and holds the lock through the mutation.
It therefore cannot restart the senders across a concurrent freeze. PostgreSQL,
Redis, and Elasticsearch remain available for diagnosis. This preserves
approval/audit and publisher state.

Postiz `v2.23.0` returning success from `DELETE /public/v1/posts/<id>` does not
prove its Temporal workflow stopped. A `500` is also indeterminate. The caller
must re-read the project-scoped post window, then terminate and verify the exact
scheduler workflow:

```sh
sudo dholbeat-publisher-control terminate-post-workflow --post-id POST_ID
sudo dholbeat-publisher-control verify-post-workflow-stopped --post-id POST_ID
```

Only a supported Temporal workflow description returning a concrete non-running
status is cancellation evidence. A missing workflow, invalid response, query
failure, or `RUNNING` status fails closed; keep the global switch frozen and do
not retry a provider write.

Unfreeze only after the incident cause, current final approval/hash, mapping,
idempotency receipts, provider state, and pending Temporal workflows are
reviewed:

```sh
sudo dholbeat-publisher-control unfreeze --confirm UNFREEZE-PUBLISHER
```

The command retains the marker and stops both senders again if health does not
return within the bounded 15-minute cold-start window.

## Application-aware backup

WP-07 invokes the adapter under its host-global non-overlap lock. Use a unique
lowercase backup ID. A restore-evidence backup must name one scheduled fixture
post whose exact Visibility query returns one result before quiescence:

```sh
sudo dholbeat-publisher-state backup --backup-id BACKUP_ID \
  --visibility-control-post-id FIXTURE_POST_ID
sudo dholbeat-publisher-state verify --backup-id BACKUP_ID
```

The adapter stops Postiz, Temporal, and Redis; dumps both PostgreSQL databases;
copies Redis AOF state only while Redis is stopped; creates an Elasticsearch
filesystem snapshot; and hashes every file. Redis uses a retained volume,
`appendonly yes`, and `noeviction`: DG-01 proved no Postiz state rebuildable, so
it cannot be discarded until a later exact live behavior drill proves that safe.
The adapter restores Redis after the copy and restarts the two senders only when
the global kill switch was not already active. WP-07 must write the verified
directory directly to encrypted restic, then purge that exact staging child;
staging has a 4 GiB bound and one-day maximum age. Copying live PostgreSQL or
Elasticsearch directories is forbidden.

## Disposable restore

Restore only to a fresh project matching
`dholbeat-publisher-restore-<id>` and an unused loopback port:

```sh
sudo dholbeat-publisher-state restore-disposable --backup-id BACKUP_ID \
  --project-name dholbeat-publisher-restore-DRILL_ID --loopback-port 15001
```

Before creating a container, the adapter renders the exact operator-selected
Compose merge and requires the validated disposable project name, internal-only
attached networks, disabled Postiz cron, and a read-only snapshot mount. It also
requires enough Docker-filesystem space for twice the backup size while
preserving 8 GiB free. The receipt binds those effective controls by SHA-256 and
passes only when Postiz organization count, retained Redis key count, Temporal
running-workflow count, all file digests, and the exact Visibility control match
the backup. That key-count check proves the retained bytes loaded; only the
later exact scheduling drill can prove whether Redis is behaviorally
rebuildable.

The default command removes the exact disposable project, networks, and volumes
on success or failure; it emits a verified result only after successful cleanup.
For a bounded live inspection, add `--keep`; this is an explicit temporary disk
exception and must be followed immediately by:

```sh
cd /opt/dholbeat/publisher
docker compose --file compose.yml --file compose.restore.yml \
  --project-name dholbeat-publisher-restore-DRILL_ID down --volumes --remove-orphans
```

A production restore is not this command. It requires the WP-07/WP-20 reviewed
release, founder confirmation, a frozen publisher, a new destination or explicit
production recovery plan, and reconciliation before any sender is unfrozen.

## Update and rollback

1. Keep the global switch frozen. Take and disposable-restore a fresh backup
   with an exact Visibility control.
2. Measure host disk before and after pulling the candidate digest. Stop unless
   at least 8 GiB remains while old and new image sets coexist; do not delete the
   rollback image to make the plan fit.
3. Review migrations and the previous release's compatibility. A Git revert is
   not a database rollback.
4. Apply the candidate only through an annotated cross-reviewed release and
   byte-identical `infra-plan` digest. Budget at least 15 minutes for readiness.
5. Repeat authorization, registration-lock, backup/restore, scheduler
   termination, immediate/scheduled/cancel/delete, and capacity probes using
   fixtures or the separately approved canary.
6. On failure, keep the switch frozen. Reapply the preceding exact release. If
   migrations are not backward-compatible, restore the pre-update Postiz DB,
   Temporal DB, and Elasticsearch snapshot together. Verify the exact
   Visibility control before considering unfreeze.

Do not clean old images until the rollback window closes and a fresh post-update
snapshot passes disposable restore.

## Explicit decommission after activation

`publisher_enabled: false` is an admission/apply gate; changing it does not
claim that already-running containers stopped. To decommission an activated
publisher, use a separately reviewed exact-host change, then:

```sh
sudo dholbeat-publisher-control freeze --reason 'reviewed publisher decommission'
cd /opt/dholbeat/publisher
sudo docker compose down --remove-orphans
sudo dholbeat-publisher-control status
```

Require an empty running-service set and retain the kill-switch marker. Never
add `--volumes` to this command: PostgreSQL, Redis, and Visibility destruction is
a separate destructive recovery decision requiring a verified backup and exact
volume names. Commit `publisher_enabled: false` with the reviewed decommission
receipt so later applies cannot reactivate the stack accidentally.

## Seven-day canary and stop conditions

Before a real brand account is admitted, record seven continuous days with no
OOM, less than 4.5 GiB peak publisher RAM, less than 18 GiB steady host disk,
at least 8 GiB update headroom, and Postiz `/tmp` below 80% of its 256 MiB
tmpfs. Exercise the global kill switch and one scheduler-verified cancellation.
Any threshold breach stops admission and returns measured
prune/scheduling/upgrade options to the founder; it does not raise a limit or
purchase a larger VPS automatically.

## Credential rotation

Rotate one boundary at a time from a fresh backup. Update only the matching SOPS
value, apply the reviewed plan, verify the consumer, then revoke the old value.
Postiz JWT rotation invalidates sessions. Database/cache rotation requires a
coordinated application and state-service change while frozen. R2 rotation must
prove the new key reaches only the public media bucket and the old key is
revoked. A leaked age recipient requires rotating every underlying value, not
merely re-encrypting historical ciphertext.

## Monthly cost

| Component | Monthly change | Complete boundary |
| --- | ---: | --- |
| Postiz and state software | $0 | AGPL/PostgreSQL/BSD/Elastic/MIT images, all self-hosted |
| Existing approved `publish-1` Linux6GB | $0 new in WP-13 | $7/month host already approved |
| Public media and private restic R2 | $0 new in WP-13 | Remains within the shared expected $0–1/month baseline |
| **WP-13 incremental cost** | **$0/month** | No paid tier or capacity increase |

A measured `publish-1` upgrade to Linux12GB would raise infrastructure from
about $14–15/month to $21–22/month and requires a fresh founder decision.

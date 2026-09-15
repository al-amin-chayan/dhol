# Publisher production acceptance — 2026-09-15

Refs #14, #15, #17. Author: Codex. Source cross-review: pending.

The founder explicitly instructed deployment of the functional infrastructure
before one complete final PR. Production now runs all six pinned Postiz services;
registration is closed, with two existing organizations, zero integrations and
zero posts. No real social provider was connected or called by these drills.
This is a provisional functional rollout, not a claim that the new source head
has been cross-reviewed or that an official new release receipt exists.

## Failures found and resolved

1. The LXC host cannot loop-mount the bounded backup image. The restricted
   `fuse2fs` mount helper provides the same 2 GiB filesystem bound through
   `/dev/fuse`. UID 1000/GID 0 write/read/purge and mount restart passed before
   installing Docker's mount dependency. Stopping that mount now stops Docker.
2. nginx interpreted the host's exposed CPU count as 96 workers. Postiz also
   repeatedly compiled identical Temporal workflow bundles, causing cgroup OOMs
   despite a superficially healthy API. Two nginx workers, bounded log streams,
   three-application health and guarded original-SDK bundle reuse resolved the
   observed failure. Total hard memory limits remain 4,608 MiB. Six runtime
   tests passed under the exact pinned image, including incompatible-SDK
   rejection, bundle variants, bypasses and stricter provider limits.
3. Application dumps and restored directories inherited the service's private
   umask. Explicit traversal/snapshot permissions preserve Elasticsearch access
   without relaxing SQL exports or Redis's enclosing private directory.
4. The vendor's Prisma wrapper downloaded packages at startup. The pinned
   image's bundled Prisma 6.5.0 now starts without those downloads; the real
   outbound-blocked application restore passed.
5. Restic stored uploaded relative bundle files at snapshot-root paths. Source
   recovery now dumps those exact paths, with existing quotas and process
   cleanup. Both a real-restic regression and actual encrypted R2 recovery passed.
6. Unsigned private R2 reads returned a specific HTTP 400 XML authorization
   error. Accept only that exact bounded response or 403; arbitrary 400s remain
   failures. Explicit verifier user agents avoid an unrelated WAF rejection.
7. An internal-only disposable Docker network cannot serve the host-loopback
   fixture probe. The optional container HTTP adapter validates the exact owned
   fixture/restore Compose project and calls only its local API via Node.
   The full live generic matrix passed through it without opening egress.
8. A freeze marker may arrive while a backup holds the host lock. Backup recovery
   now checks that marker again before starting senders. The injected failure
   test proves Redis can recover while Postiz and Temporal remain stopped.

## Live acceptance

| Scope | Actual result | Remaining closure condition |
| --- | --- | --- |
| #14 route and storage boundaries | 23-resource no-change plan, independent native tunnel origin proof, founder browser access, seven-case machine/API credential matrix, private S3 denial, signed media roundtrip, direct-origin/state-port negatives, native state lock/recovery and scoped delegation passed. Paperclip/imported boundaries were preserved. | Final exact-head review of verifier fixes and publication of honest reviewed acceptance receipts. No seven-day dependency. |
| #15 encrypted recovery | Host repository initialized; application-aware encrypted backup and actual systemd disposable restore passed. Independent source repository initialized; clean reviewed-main bundle and annotated tags recovered with only R2 and file-protocol Git. Backup/age-health timers are active. | Password-manager attachment updates and byte-identical readbacks, including initialized repository pins, independent root and bootstrap kit; final exact-head review/release reconciliation. No seven-day dependency. |
| #17 publisher | Six healthy pinned services, closed-registration negative, 17-case generic tenant/API-key/scheduling matrix, exact Visibility snapshot/restore, restored API access and scheduler-confirmed cancellation passed. All disposable resources were removed and production recovered. | Seven-day capacity evidence, exact-head review of the fixture/first-version limitations below, and final reviewed release/dependency receipts. Real-provider publication/refresh remains the explicitly later admission gate. |

The founder-browser positive and CLI machine/negative matrix are separate
proofs. No founder Access JWT was exported; the CLI's `complete: false` field
was not rewritten. A database fixture is not successful provider publication or
OAuth-refresh evidence. These operations do not authorize a real-provider canary.

The successful generic backup retained one future scheduled post and restored
its exact organization, date, API visibility and Temporal Visibility hit count
(one). API cancellation was followed by supported Temporal description showing
`TERMINATED`; HTTP deletion alone was never treated as scheduler cancellation.

Application snapshot
`c5d284df990323bbf073cf35d13f46d35451e78a7b8fd9eb3fc69b0ef5843500`
was restored in 99.415 seconds with cleanup. The fresh post-canary-start backup
`47d41bee1418bb347a32a996c921508d94a4c6dc4081dde5c9d8927e8df7f41a`
contained 9,584,819 staged bytes and completed in 81.135 seconds. Daily retention
may supersede earlier same-day snapshots; historical proof is not a promise
that a superseded snapshot remains retained.

Source snapshot
`b727e092ed8eebb945bc12189976f5751a6fafe2387c649b6bcee52a3d3403c2`
contains reviewed main `e1650af2d50c0960403ebf70c8507eed44d879db`, tag
`infra-prod-20260915-1`, and all annotated production tags. The verified
unadopted core release catalog entry is null; its legacy backups were preserved.
The source kit recovery used no original checkout mount and removed its new
clone/downloads afterward. Its root was read from a protected local export,
so this does not substitute for password-manager download verification.

## Seven-day observation

The actual measurement started September 15 at 12:28:38 Bangladesh time;
earliest time completion is September 22 at 12:28:38. The five-minute host
timer requires seven elapsed days, at least 2,016 samples, an observed Redis
AOF rewrite, no continuity gap over fifteen minutes, and all capacity limits.
One real backup maintenance cycle passed with the observer active. OOM and
unexpected restarts were zero; conservative summed memory peaks were about
3.28 GiB, disk used about 11.83 GiB and free space about 17.45 GiB.

This observes the production stack after isolated generic acceptance; it is
not seven days of successful real-provider traffic. The first rollout has no
previous accepted application version. Exact pinned-image recovery is proved;
a future different-version migration still requires the documented frozen
backup, compatibility review, candidate/preceding-image coexistence and rollback
drill. Do not invent a historical version-upgrade result to satisfy review.

## Review evidence and final reconciliation

Private execution logs, plans and receipts remain gitignored in this lane's
`.artifacts/`; they must not be uploaded as unrestricted CI artifacts. The
principal evidence files are `publisher-generic-fixture-visibility-acceptance.log`,
`publisher-encrypted-application-restore-final.log`,
`source-escrow-kit-bootstrap-recovery.json`,
`publisher-live-credential-matrix.json`, `founder-browser-positive.json`,
`publisher-direct-state-origin-negative.json`,
`publisher-scheduled-backup-canary-maintenance-proof.log`, and
`publisher-final-live-status.log`. The controller's complete author check is
saved as `final-check.log`.

After password-manager readbacks, publish one complete ready PR and its exact
head for founder-triggered Claude review. Following approval, merge/promotion
and legitimate reviewed dependency receipts, reconcile an annotated release
through the normal exact-plan controller, then verify no-change and refresh
the independent source bundle/root records. Never fabricate reviewed heads,
reset a failed canary, or declare #17 complete merely because seven days elapsed.

There is no new paid subscription or VPS upgrade. Software adds $0/month;
existing $7/month host and shared expected $0–1/month R2 baseline are unchanged.

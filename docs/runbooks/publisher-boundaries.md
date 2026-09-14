# Isolated publisher boundary rollout

WP-06A (#12/PR67) adopted the existing Cloudflare zone, tunnels, DNS and team
Access configuration without changes. WP-06B adds only publisher UI/API Access,
the private core/publisher backup and independent source-escrow buckets, and the public publisher media
bucket/domain/lifecycle. Core routes, the team UI, and unrelated zone objects
must remain no-change. This lane does not activate unrelated n8n/webhook paths.

### Computed observations after the initial create

The 2026-09-14 create completed its provider changes, but its final guard rejected
three read-only observations: R2 domain ownership/TLS became active; attaching
the founder policy to both approved publisher applications changed `app_count`
from 1 to 3; attaching the new machine policy to the API changed its count from
0 to 1. The original command did not emit a successful apply receipt. See the
[redacted diagnostic](../evidence/publisher-routing-create-2026-09-14.json).

The routing guard recognizes only these precise convergence transitions in an
entirely no-change plan. Drift records must match the current resource exactly,
preserve identity and every other attribute, and contain no unknown, imported,
moved, duplicate or unrelated object. Count changes beyond those reviewed
attachments, domain failure/deactivation, selector changes and all other drift
still require separate review. The standalone seven-object adoption guard
continues to reject every drift record. Cloudflare's locked provider declares
[`app_count`](https://raw.githubusercontent.com/cloudflare/terraform-provider-cloudflare/v5.24.0/docs/resources/zero_trust_access_policy.md)
and domain
[`status`](https://raw.githubusercontent.com/cloudflare/terraform-provider-cloudflare/v5.24.0/docs/resources/r2_custom_domain.md)
read-only.

Do not rerun the old creation digest after this failure. Preserve a fresh
encrypted state snapshot, promote this fix through opposite-model review, and
run a fresh `scripts/cloudflare plan` on that reviewed release. It must prove
the complete twenty-three-object no-change profile before preparing a host
apply. A successful read-only check on an author branch validates the fix; it
does not replace the reviewed production receipt or the required route probes.
The saved diagnostic is not a WP-06B gate or an issue-closure receipt.

The native host-planning capture also reads `/accounts/{account_id}/access/organizations`
to obtain the current Access authentication domain. Its operator API token must
have `Access: Organizations, Identity Providers, and Groups Read` in addition
to the existing routing reads. The old bootstrap API token returned HTTP 403
at this endpoint after the candidate routing guard passed. An independent MCP
read succeeded, but cannot replace that mandatory native capture. Grant the
missing read access through a prepared, founder-approved temporary verifier
token; keep it outside Git and production hosts, and revoke it after rollout.

## Review and exact-plan sequence

1. Run `scripts/check` and `scripts/cloudflare validate` with the existing
   `--credentials`, `--founder-key`, `--break-glass-key` private operator inputs
   and `--confirm cloudflare-control-plane`. These must be distinct regular
   mode-0600 files outside every checkout; never paste their contents in chat.
   Validation uses locked native OpenTofu/provider binaries and both age roots.
2. Publish the implementation as a ready PR into `develop` with
   `review:requested`, exact head SHA and these runbooks. The founder starts
   Claude's baseline review. Promote approved code through a reviewed
   `develop` → `main` merge and annotate the merge commit with a production tag.
3. Run `credential-plan-access`. Review its digest/account/name/non-expiring lifetime,
   then confirm `credential-issue-access --approved-digest <digest> --release
   <tag> --review-pr <promotion-PR>`. Both use the private input options above.
   Issuance produces only `publisher-access.sops.yml` in ignored evidence,
   verifies both recipient MAC recoveries, and returns the public token ID.
   Copy ciphertext into the corresponding reviewed secret lane and independently
   escrow the credential in the password manager. Existing same-name tokens
   fail closed rather than silently replacing secrets.
4. Run `routing-plan`. The plan permits only creation of the sixteen declared
   publisher resources; all seven imported objects remain unchanged. The
   approval digest binds source input hashes, current encrypted state,
   service-token identity and complete new configuration. Confirm exactly that
   digest with `routing-apply` and the reviewed release/PR options. A fresh plan
   must match; apply uses its encrypted native binary plan. The post-apply
   native plan must be no-change and a new encrypted recovery snapshot is saved.
5. Run `credential-plan-storage`, review the four bucket-only object-write
   credentials, then confirm `credential-issue-storage` with its digest/release/PR.
   This retrieves the existing publisher tunnel token and immediately encrypts
   each issued root into a separate complete secret set. If escrow fails, only
   the newly issued unescrowed credential is revoked. Earlier successfully
   escrowed credentials remain recoverable; inspect partial receipts before retry.
   A token-management credential able to inspect account permission groups and
   issue bucket-scoped tokens is required; the old #12 temporary token cannot
   perform this operation. Do not substitute a broad runtime credential.
6. Commit only recovered ciphertext under `.sops.yaml`: `publisher-tunnel`,
   `publisher-access`, `core-backups`, `publisher-backups`, `publisher-media`,
   and `source-escrow` each have separate catalog scopes. Runtime publisher
   application secrets stay in `publisher.sops.yml`; the role combines just
   those four values with its two media credentials. Founder/break-glass age
   private keys and independent provider recovery roots stay outside Git.
7. On the reviewed production checkout, regenerate `scripts/cloudflare plan`
   after routing apply. It detects the managed profile, proves the complete
   twenty-three-object no-change inventory and captures real Access audiences/team
   name. Set `cloudflared_enabled: true` through a reviewed publisher-only
   inventory change. Generate the exact `infra-plan --limit publish-1`, then
   obtain founder confirmation before `infra-apply`. The host role requires
   the routing no-change receipt, installs the locked cloudflared binary,
   root-only token file, source-derived ingress and origin Access JWT validation.
   Application ports stay loopback-only. A publisher not yet adopted may remain
   controlled-unavailable until #17; that is not application health evidence.

## Required evidence and rollback

After installation, run routing verification and the existing host public
listener verifier. Capture anonymous/wrong-founder denial, scoped founder
acceptance, API token denial/acceptance, token rejection at UI/outside API,
alternate-host denial and direct-public-IP denial. Positive API probes also
need the independent Postiz API key; Access admission alone is insufficient.
Do not invoke a publishing endpoint. Keep auth values in private operator
inputs and emit only status categories. Verify no backup bucket has an enabled
`r2.dev` or custom public domain; verify public media objects expire and cannot
expose backup/config objects. An empty media bucket's 404 is not an object
delivery/lifecycle proof. Missing sessions, missing app key or undeployed route
must be recorded as incomplete, never accepted.

Record the exact release, reviewed source head, provider plan digest, twenty-three
resource IDs, connector count, route results, parent-delegation/auto-renew
verification, state lock/drill and remote encrypted recovery receipts. Existing
WP-06A verification remains available through `verify`, `recovery-drill` and
`delegation-drill`. #14 closes only after real WP-06B evidence is committed as
redacted receipts and cross-reviewed; #15 follows the backup recovery runbook.

Before changes, preserve the pre-apply encrypted state snapshot and the
current publisher connector configuration. For host rollback, restore the
reviewed prior ingress/config and restart only the publisher connector. Recheck
the unchanged team route, core routes and negative public-IP probes. If a new
route must be withdrawn, plan that specific change in a new reviewed lane;
this create-only controller deliberately refuses deletion/update/replacement.
Never restore a stale whole-zone state or destroy imported objects as a route
rollback. Keep backup repositories and independent roots intact. Rotate only
the exposed dedicated service token, tunnel token or bucket credential using
its catalog procedure; the existing shared operator R2 root is not a runtime
credential and must not be revoked incidentally.

The founder selected a non-expiring runtime service token on 2026-09-14 to
avoid recurring renewal and surprise outages in a one-person operation. The
issuer requests `duration: forever`, supported by the current
[Cloudflare API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/service_tokens/methods/create/),
and verifies the returned lifetime before accepting the token. There is no
scheduled expiration or monthly renewal. The token is accepted only by the
specific publisher API Access policy; it does not replace the independent
project-scoped Postiz API credential. A leaked token remains usable until it
is disabled, rotated or revoked, so keep its recovery record in the password
manager and its runtime value in the dedicated SOPS set.

For an exposure, go to Cloudflare Zero Trust > Access controls > Service
credentials > Service Tokens and disable the named
`dholbeat-n8n-publisher-api` token immediately. This stops API access until
recovery. Cloudflare also supports rotating the client secret or deleting the
token. Escrow the replacement, update the n8n credential, prove the positive
and negative route probes, and invalidate the old secret. Do not assume a
Cloudflare dashboard change updates n8n or committed recovery ciphertext.
Replacing the token ID also changes the Access policy selector and requires
a separately reviewed explicit plan; do not weaken the create-only guard.
See [Cloudflare service-token controls](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/).

The temporary account-management token remains short-lived and must be revoked
after rollout; the non-expiring choice applies only to the runtime API service
token. No account-management credential is installed on a production host.

`infra-plan` refreshes the real provider plan before Ansible and again afterward,
requiring identical normalized source, encrypted-state and Access authority.
Operator capture/render requires an observation no older than five minutes.
`infra-apply` repeats that host plan, compares its byte-identical digest to the
approved plan, and refreshes again immediately after founder confirmation.
Changes to source/state/Access invalidate approval; capture time and encrypted
plan randomness do not. The role validates the captured source/state/Access
authority without timing the founder's response, so confirmation can take longer
than five minutes. A stale artifact cannot replace the mandatory live captures.

All added software is free. R2 has usage costs, documented with bounded
retention in [backup recovery](backup-recovery.md); no new subscription is
introduced. The public media lifecycle is seven days (604800 seconds) with
one-day incomplete multipart abort (86400 seconds), per the locked provider's
[lifecycle schema](https://raw.githubusercontent.com/cloudflare/terraform-provider-cloudflare/v5.24.0/docs/resources/r2_bucket_lifecycle.md).

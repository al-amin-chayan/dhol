# DG-01 — Self-hosted publisher selection

| Field | Value |
| --- | --- |
| Gate | `DG-01 publisher` (`docs/plans/two-vps-reproducible-implementation-plan.md` §7) |
| Status | **decided — Postiz** |
| Evidence run | `infra/tests/publisher-eval/run.sh`, 2026-08-25 |
| Unblocks | `WP-13` (`publish-1` and the selected publisher adapter), then `WP-17` |
| Decision date | 2026-08-25 |
| Deciding human | Al Amin Chayan (founder) |

## Question

Which self-hosted publisher does `publish-1` run: Postiz, or Mixpost — and at
which exact edition?

The founder-approved multi-project requirement (`README.md` §9) makes this a
capability test, not a preference: the deployed edition must give each project
its own tenant, must expose a machine credential n8n can use, and must refuse a
credential belonging to another project.

## Candidates

Pinned in `infra/tests/publisher-eval/candidates.yml`.

| Candidate | Edition | Version | Licence | Price | Evaluated? |
| --- | --- | --- | --- | --- | --- |
| Postiz | single self-hosted edition | `v2.23.0` | AGPL-3.0-or-later | $0 | yes |
| Mixpost | Lite | `v2.6.0` | MIT | $0 | yes |
| Mixpost | Pro | — | proprietary, internal use only | $299 one-time | **no** |
| Mixpost | Enterprise | — | proprietary, resale permitted | $1,199 one-time | **no** |

Images, by digest:

```text
ghcr.io/gitroomhq/postiz-app:v2.23.0@sha256:785f97312f66a347fb96cdccc4ded5a33ced69a672c89a9adc8054e7d6a21dc5
inovector/mixpost:v2.6.0@sha256:90cf94cec73dcaf87989d30b0de7a84b0625ff06797ba61c8ecb54e8fe1e10c4
```

The Pro and Enterprise images (`inovector/mixpost-pro-team`,
`inovector/mixpost-enterprise`) require a `LICENSE_KEY` at runtime. DG-01
authorises no purchase, so **every Pro and Enterprise capability in this
document is an unverified vendor claim** and is never compared against a
measured result.

## Evidence

Reproduce with [`../runbooks/publisher-evaluation.md`](../runbooks/publisher-evaluation.md).

Both candidates ran the same seventeen-check fixture matrix: three generic
project fixtures (two with a channel, one without), the tenant's own positive
path, and the negative authorization, credential-rotation, registration-lock
and dump/restore cases. Channels are database fixture rows. **No social
account, OAuth grant, provider call or purchase was involved.**

A cross-tenant rejection is only recorded as isolation evidence when the
identical request is accepted for the tenant's own channel, so a malformed
request body cannot be mistaken for an authorization boundary.

### Result summary

| | Postiz `v2.23.0` | Mixpost Lite `v2.6.0` |
| --- | --- | --- |
| Verdict | `viable-with-findings` | `disqualified` |
| Checks passed | 17 / 17 | 2 / 17 |
| Checks failed | 0 | 2 |
| Checks unsupported | 0 | 13 |
| Drills passed | 1 / 3 — see finding 3 | 2 / 2 |
| Tenant model | organization | none |
| Machine API | `/public/v1`, `Authorization: <key>` | none |
| Cold start to first API answer | 29-59 s, one restart never completed | 20-329 s |
| Peak RAM (whole topology) | 2,647 MiB | 849 MiB |
| Topology disk, images plus volumes | 5,473 MiB | 1,887 MiB |
| Update headroom | not measured | not measured |

**Topology disk is a lower bound, not host usage.** It counts this topology's
images and named volumes only; the host OS, container writable layers, Docker
metadata and logs, monitoring and restic all sit outside it. **Update headroom
is not measured at all.** `WP-13` wants at least 8 GB free on a 30 GB host while
two image sets coexist during an upgrade, and nothing here observes a real
filesystem or performs an upgrade. Subtracting this footprint from 30 GiB would
be arithmetic wearing a measurement's clothes, so the harness reports it
`unmeasured` and the verdict does not gate on it. `WP-13` must produce that
figure on the real host.

Read the cold-start row as evidence that convergence is slow and
contention-sensitive on a small host, not as a comparison between the two
products: both figures are single samples on a shared laptop runtime and both
candidates varied by several minutes between runs. See the limitations section.

### What disqualifies Mixpost Lite

Two independent grounds, both measured:

1. **No tenant boundary.** The application route table has 49 routes and
   **zero** workspace routes. A label created by the first login is returned
   verbatim to a second, unrelated login: every authenticated user shares one
   global set of accounts, posts, media and labels. Two projects on one Lite
   instance would share one channel list and one media library.
2. **No machine API.** Excluding the Laravel Horizon dashboard, the route
   table contains **zero** API routes. Every write path is a session-and-CSRF
   browser route. n8n has nothing supported to call.

A third finding, not disqualifying but relevant to any deployment: the Lite
image ships a pre-created `admin@example.com` account and nothing forces a
password change. Keep the two claims apart by their evidence.
The harness measures only that the account exists — it records
`ships_default_admin_account: true` and never attempts a login. That the
documented default password actually authenticates on a fresh instance is a
**manual observation made during exploration, not harness evidence**; no check
in the fixture matrix reproduces it. Treat it as a caution to re-verify by hand
before any Lite deployment, not as a measured result.

Mixpost Lite is the lightest option by a wide margin and its dump/restore drill
passed. Neither fact reaches the requirement.

### What Postiz demonstrates

| Check | Result |
| --- | --- |
| Three distinct organizations from three registrations | pass |
| Per-organization public API key | pass |
| Tenant lists only its own channel | pass |
| Tenant A addressing tenant B's channel directly by id | rejected, 404 |
| Unauthenticated public-API call | rejected, 401 |
| Unknown credential | rejected, 401 |
| Tenant A's key scheduling into tenant B's channel | rejected, 400, while the identical shape into its own channel returned 201 |
| Tenant A's post invisible in tenant B's post window | pass |
| Tenant B deleting tenant A's post | post survived |
| Rotated key | previous key rejected, 401 |
| Schedule, list, cancel through the machine API | pass |
| `DISABLE_REGISTRATION=true` after bootstrap | new registration rejected |
| `pg_dump`, schema drop, reload | all organizations preserved |

### Postiz findings that constrain `WP-13`

1. **Elasticsearch is not optional.** Temporal has been required since Postiz
   `v2.12.0`. Running Temporal on its own PostgreSQL visibility store — the
   obvious way to save roughly a gigabyte on a 6 GB host — makes the Postiz
   backend fail to start:

   ```text
   Unable to create search attributes: cannot have more than 3 search attribute of type Text.
   ```

   The minimum viable topology is therefore six containers: Postiz,
   PostgreSQL, Redis, Temporal, Temporal's PostgreSQL, and Elasticsearch 7.17.
   This is a measured constraint, not an upstream recommendation.
2. **A project tenant costs a login.** Postiz exposes no create-organization
   endpoint. A new organization exists only as a side effect of registering a
   new user, so onboarding a project means opening registration, registering
   that project's account, and closing registration again. That toggle needs a
   runbook step and an owner; it is a footgun, not a blocker.
3. **Cancelling a post does not stop it. Measured, on an untouched instance.**
   `DELETE /public/v1/posts/<id>` returns 200 and the row disappears, but the
   Temporal workflow that would send the post is still `RUNNING` a minute
   later. At `v2.23.0` `deletePost()` removes the row first, then performs the
   visibility lookup and termination inside catch-and-ignore blocks and returns
   regardless, so a failure there is invisible to the caller. This is not a
   restore artefact: the same drill fails on a freshly converged instance that
   has never been rebuilt.

   This matters more here than it would elsewhere. `README.md`'s hard rule is
   that nothing publishes without human approval, and the plan requires that
   editing after approval "prevents/cancels an unsent stale publisher job". A
   workflow that outlives the post row is exactly such a job, and the
   publisher's own cancel API does not demonstrably stop it. **What the orphan
   then does was not tested** — whether it publishes stale content, errors, or
   no-ops is unknown, and assuming the benign case would be exactly the kind of
   guess this evaluation exists to avoid.

4. **Cross-tenant delete answers 500, not 403.** The post correctly survives,
   so the boundary holds, but the error path is wrong. n8n must treat a 500
   from a delete as *indeterminate* and re-read state, never as *deleted*.
5. **Upstream ships no backup documentation, and Temporal's database is not
   rebuildable.** The dump/restore procedure is ours. The obvious reading —
   that Temporal is a workflow engine and can simply be re-provisioned — is
   wrong here: a scheduled post is a Postiz row *plus* the Temporal workflow
   that sends it, and at `v2.23.0` the recovery scan only re-queues posts whose
   publish time is already past. Rebuild Temporal empty and every *future* post
   comes back as a row that never fires until it is late. Temporal's PostgreSQL
   is therefore retained state and belongs in the backup contract. Only the
   Elasticsearch visibility index is genuinely rebuildable. The drill proves
   this by destroying both and requiring the restored post to be queued with an
   open workflow behind it.
6. **The upstream Compose file is not deployable as-is.** It pins `:latest`,
   publishes database ports, and ships pgAdmin, Sentry Spotlight, Temporal UI
   and `temporal-admin-tools`. None of those may reach `publish-1`.
7. **Cold start is slow and highly variable, and a restart can wedge.** On a
   quiet machine the backend answered 29-59 seconds after the converge command.
   On a machine also running unrelated containers, several runs never answered
   inside a ten-minute budget and were abandoned, and one run's backend never
   came back at all within twenty minutes after a container recreate — the
   evaluation restarts Postiz twice, once for the restore rebuild and once for
   the registration lock, and the second restart is where it wedged. Six containers, a JVM, and Prisma
   migrations do not degrade gracefully when memory and I/O are contended, and
   `publish-1` is a 6 GB host that will also run monitoring and restic. Restart
   time is therefore a real operational property: the restart window,
   health-check grace periods, and any update-rollback drill must budget
   minutes and tolerate a much worse tail. This is the single most likely
   surprise during `WP-13`.
8. **AGPL-3.0-or-later.** The `LICENSE` file at the pinned tag
   ([`v2.23.0`](https://github.com/gitroomhq/postiz-app/blob/v2.23.0/LICENSE))
   grants the GNU Affero General Public License "either version 3 of the
   License, or (at your option) any later version". The exact identifier is
   therefore `AGPL-3.0-or-later`, not `AGPL-3.0-only`, and the licence of
   record is read from the immutable tag rather than from `main`. Self-hosting
   for the founder's own brands is unrestricted. If a modified Postiz were ever
   exposed over a network to third parties, §13 of AGPL-3.0 would require
   offering the corresponding source. Running it unmodified for our own brands
   does not trigger that.

## Acceptance-criteria disposition

Issue #16 lists more than this evaluation measured. Closing a gate while some of
its criteria are simply absent from the packet would make the gate mean less
than it claims, so every criterion is dispositioned here. `deferred` items are
bound to a named later gate, not quietly dropped.

| Criterion from #16 | Disposition | Where it stands |
| --- | --- | --- |
| Exact editions, versions, licences pinned | **met** | `candidates.yml`, digest-pinned; licence read from the immutable `v2.23.0` tag |
| Project/workspace authorization, API ownership | **met** | seventeen-check matrix, both candidates |
| Scheduled create, list, cancel/delete | **met for the post row, not for the job** | `posts.schedule`, `posts.list`, `posts.cancel`; cancellation re-reads the window and the row is gone. The `cancel.terminates-workflow` drill shows the underlying workflow is not stopped — finding 3 |
| Immediate publishing (`type=now`) | **deferred to `WP-13` canary-account gate** | never exercised: `create_post` in `infra/tests/publisher-eval/probe.py` always sends `type=schedule` with a future date. A genuine `type=now` call against a database-fixture channel would attempt a real provider call, which DG-01 forbids, so no provider-safe drill is possible here; it runs against the same founder-approved canary connection as token refresh, below |
| Token refresh behaviour | **deferred to `WP-13` canary-account gate** | needs a connected provider account, which DG-01 forbids here. No synthetic substitute is honest: refresh is provider behaviour, not publisher behaviour. Runs against a founder-approved canary connection, per the sequence in Founder decision |
| Application-aware backup/restore | **met** | restore-after-rebuild drill: Postiz and Temporal databases destroyed and reloaded from dumps, Elasticsearch rebuilt from empty, then login, credential, own-channel, tenant boundary, and a pending post still queued with an open workflow behind it |
| 6 GB / 30 GB footprint | **partly met** | peak RAM and topology disk measured; host steady usage is a lower bound only |
| Update headroom | **not met — unmeasured** | needs a real 30 GB host mid-upgrade; the harness reports `unmeasured` rather than a computed pass |
| Update rollback | **deferred to `WP-13`** | no pinned upgrade/rollback drill was run; the evaluation converges one version |
| Duplicate-post controls | **deferred to `WP-13` canary-account gate, with a measured caveat** | Postiz `v2.23.0` advertises duplicate-post protection; demonstrating it needs the same canary-account drill as token refresh. Measured here: a cancelled post's workflow keeps running, so the kill switch cannot be built on the cancel API alone — see finding 3 |
| Registration control | **met** | `registration.lock` drill, gated on the backend being ready first |
| Access / service-token integration fit | **met, by inspection not measurement** | see below |
| Maintenance burden | **met, by inspection not measurement** | see below |
| Full monthly wallet | **met** | Cost section |

### Access and service-token fit, and maintenance burden

Neither is measurable on a disposable local instance, and both are decided by
architecture rather than behaviour, so they are compared by inspection and
labelled as such.

**Access and service-token fit.** Both candidates present a single HTTP origin
that binds to loopback and publishes through the host's own Cloudflare tunnel,
so both sit behind founder-only Access identically. The difference is what n8n
can then use. Postiz accepts a per-organization API key in an `Authorization`
header, so an Access service token plus that scoped credential is exactly the
two-factor machine route `WP-13` specifies. Mixpost Lite exposes no machine
API, so an Access service token would front a surface n8n cannot call — the
service-token design has nothing to authenticate against. This follows from the
measured route table rather than adding a new claim.

**Maintenance burden.** Postiz is six containers including a JVM and a workflow
engine, three of which are state that must be backed up or deliberately
classified rebuildable, and its cold start is slow and contention-sensitive.
Mixpost Lite is three containers with one database. On maintenance alone
Mixpost Lite is the lighter system by a clear margin; it simply cannot do the
job. This is recorded so the founder sees what the capability is costing, not
to reopen the comparison.

## Cost

`README.md` §6 tracks the platform's *marginal* cost separately from the
$14/month VPS bill. The table below is the complete wallet, so it is
deliberately larger than §6's marginal figure.

| Line | Postiz | Mixpost Lite | Mixpost Pro | Mixpost Enterprise |
| --- | --- | --- | --- | --- |
| `core-1` VPSDime Linux6GB | $7.00 | $7.00 | $7.00 | $7.00 |
| `publish-1` VPSDime Linux6GB | $7.00 | $7.00 | $7.00 | $7.00 |
| Cloudflare R2, private restic plus public media | $0–1 | $0–1 | $0–1 | $0–1 |
| Platform marginal costs for two brands (`README.md` §6) | $10–25 | $10–25 | $10–25 | $10–25 |
| Publisher licence, first year amortised | $0 | $0 | $24.92 | $99.92 |
| **First-year monthly total** | **$24–40** | **$24–40** | **$49–65** | **$124–140** |
| **Monthly total after the first year** | **$24–40** | **$24–40** | **$24–40 plus whatever renewal buys updates** | **$24–40 plus whatever renewal buys updates** |

Neither paid edition is a monthly subscription; both are one-time purchases
tied to one domain. The amortised lines exist only so the first-year cash
impact is comparable. A $299 purchase is roughly one year of the platform's
entire approved marginal budget, and $1,199 is roughly four years of it.

Postiz and Mixpost Lite both add **$0/month** of software cost. The decision
therefore does not change the founder's wallet unless a paid Mixpost edition is
chosen.

## Reversibility

| | Postiz | Mixpost Lite |
| --- | --- | --- |
| State of record | the Postiz PostgreSQL database, **Temporal's PostgreSQL database**, and an uploads volume or R2 bucket | one MySQL database plus a storage volume |
| Export | `pg_dump`, drilled in this evaluation | `mysqldump --no-tablespaces`, drilled in this evaluation |
| Rebuildable state | the Elasticsearch visibility index | Redis queue |
| Not portable | provider OAuth tokens, which are bound to the connected account and must be re-granted on any other tool | same |

Approval state is Dholbeat's own (`WP-14`), not the publisher's. Migrating away
therefore loses unsent scheduled jobs and requires re-connecting social
accounts; it does not lose approval history, brand profiles, prompts or
generated content. Both candidates are equally reversible in this sense.

## Recommendation

**Postiz `v2.23.0`.**

It is the only $0 edition that meets the founder-approved multi-project
requirement, it met it on every negative test rather than by documentation, and
it fits the measured `publish-1` budget. Mixpost Lite is disqualified on
capability, not on cost or weight.

**Mixpost Pro: claimed sufficient, untested.** As read on 2026-08-25, the
vendor page <https://mixpost.app/pricing> advertises "Multi-tenant support",
"API" and "Webhooks" for the $299 Pro edition, and its FAQ describes workspaces
as isolated environments of which an instance may hold an unlimited number. On
those claims Pro *appears to meet* the requirement stated at the top of this
document — one tenant and one machine credential per project. Whether it also
refuses a credential belonging to another project, the third clause of that
requirement, is something no vendor page can establish. It was **not
evaluable**: the image requires a `LICENSE_KEY`, and DG-01 authorises no
purchase. So Pro is a vendor claim that has never been run, tested or measured
here, and it must never be read as a measured result — but neither is it
established as insufficient.

**Correction to an earlier rationale.** An earlier draft set $299 aside on the
grounds that the Mixpost documentation places "one user owning several
workspaces" under the **Enterprise** console
(<https://docs.mixpost.app/enterprise/configuration/multiple-workspaces>: "By
default, each user is permitted to own only one workspace"). That is true, and
it is an administrator-ergonomics property — how many workspaces a single human
login may own — not the stated tenant-and-machine-credential requirement. It is
also not a bar DG-01 applies to Postiz, where **each tenant likewise costs its
own login** (finding 2 above, "A project tenant costs a login"). Holding
Mixpost to a criterion Postiz does not meet either was not even-handed, so that
argument is withdrawn and carries no weight in this decision.

**What is decisive is cost, on its own terms.** $299 one-time is roughly one
year of the platform's entire approved marginal budget and $1,199 is roughly
four years of it. Postiz meets the requirement *as measured* at $0. Spending a
year of the marginal budget to acquire, on a vendor's word and without the
ability to test it first, a capability an evaluated $0 edition already
demonstrates is not a trade the founder's constraints support. That holds
whether or not Pro would in fact deliver what it advertises.

The recommendation was re-confirmed after this rationale was corrected: Postiz
`v2.23.0` remains the recommendation. The correction changes why the paid
editions are set aside, not whether they are.

If the founder selects Postiz, `WP-13` inherits these conditions:

1. Deploy the six-container topology. Elasticsearch is required; treat its
   disk as a declared retention surface with a named owner, alongside Temporal
   history and visibility retention.
2. Write the Compose project from scratch against `infra/services/` contracts.
   Do not adopt upstream's file. No pgAdmin, no Spotlight, no Temporal UI, no
   `temporal-admin-tools`; every image digest-pinned; every port on loopback
   behind the `publish-1` tunnel.
3. Re-measure on the production architecture before any real account is
   connected. This evaluation ran on `linux/arm64`; `publish-1` is x86-64.
4. Give the registration toggle a runbook step: registration opens only to
   onboard one project account and closes immediately afterwards.
5. Make the n8n publisher adapter treat a `500` from a delete as indeterminate.
   Separately, **do not treat a successful cancel as a stopped job**: a 200 from
   `DELETE /public/v1/posts/<id>` leaves the Temporal workflow running. The
   duplicate-post kill switch and the approval-invalidation path both have to
   verify termination against the scheduler, or stop the job by another means,
   before either can be called tested. Establish first what an orphaned
   workflow actually does when it fires.
6. Back up the Postiz database, **Temporal's database**, and uploads. Only the
   Elasticsearch visibility index may be excluded as rebuildable. Treating
   Temporal as rebuildable would leave every future scheduled post stranded
   after a host recovery; the restore runbook must say which of the three is
   retained and why.
7. Budget minutes, not seconds, for a `publish-1` publisher restart, and treat
   a restart that never completes as a case the runbook must cover rather than
   an anomaly. Set the health-check grace period and the update-rollback
   drill's timeout from a measured cold start on the real host, not from this
   evaluation's figure, and give the incident runbook a step for a wedged
   publisher restart.

## A finding that arrived after the decision

The founder selected Postiz on 2026-08-25. Finding 3 — a cancelled post's
workflow keeps running — was measured afterwards, during a later review round,
and is recorded here rather than folded silently into the existing text.

It does not change the comparison: Mixpost Lite cannot host two projects or
expose a machine API at all, so it was never the alternative this would tip
towards, and the paid editions remain unevaluated. It does change what `WP-13`
must build, and it raises a question the founder may want to answer before real
accounts are connected: whether a publisher whose cancel API does not stop the
job is acceptable given `README.md`'s human-approval rule. The evaluation's
answer is that it is workable only if the kill switch verifies termination
independently, which is now condition 5.

## Founder decision

> Recorded from the founder's explicit instruction on 2026-08-25, after reading
> this document: "my decision is go with Postiz." No agent selected or inferred
> the publisher; this section is a transcription of that decision.

- **Selected publisher and exact edition:** Postiz, the single self-hosted
  edition, AGPL-3.0-or-later, pinned at `v2.23.0`
  (`ghcr.io/gitroomhq/postiz-app:v2.23.0@sha256:785f97312f66a347fb96cdccc4ded5a33ced69a672c89a9adc8054e7d6a21dc5`)
- **Date:** 2026-08-25
- **Notes and conditions:** none added beyond this document. Selecting Postiz
  carries the seven `WP-13` conditions listed under Recommendation above, which
  are part of the decision rather than advice attached to it.

`DG-01` is closed. `WP-13` may start, and the publisher role, Compose project
and dump/restore adapter may now be committed under its own review.

Closing this gate does not close the criteria dispositioned `deferred` above.
Update rollback, update headroom on a real 30 GB host, immediate publishing,
token refresh and duplicate-post protection are `WP-13` obligations. The last
three follow a fixed sequence, not a single blanket precondition: the founder
explicitly approves a disposable or canary provider connection, the
immediate-publish, token-refresh and duplicate-post drills run against that
canary, and only then may production publishing be enabled or real brand
accounts be onboarded. They are pre-conditions on production publishing and
brand-account onboarding, not on connecting any account at all.

Changing this decision means a new dated row in the status table and a
`README.md` §10 change-log line, never a silent edit.

## Limitations

Everything this evidence does **not** cover:

1. **Architecture.** Measured on `linux/arm64` under a shared local container
   runtime, not on an x86-64 VPSDime Linux6GB host. Memory figures are a
   short-run bound on the same images, not a host measurement.
2. **Duration.** Roughly one minute of sampling per candidate, not the
   seven-day `WP-13` canary. The peak figure bounds convergence and the
   fixture matrix; it does not bound a week of scheduled work, media uploads,
   or a Postiz upgrade.
3. **No real provider.** Channels are database fixtures. Immediate publishing
   (`type=now`), token refresh, provider rate limits, media upload to a
   provider, duplicate-post protection against a live account, and OAuth
   grant behaviour are all untested here.
4. **Paid Mixpost editions are entirely untested.** Their workspace isolation,
   API authorization, footprint and restore behaviour are vendor claims.
5. **Postiz upgrade rollback is untested.** The evaluation converges one
   version; it does not upgrade `v2.22.1` to `v2.23.0` and roll back. With
   update headroom also unmeasured, the whole update story is `WP-13`'s to
   prove on the real host — see the disposition table.
6. **`DISABLE_REGISTRATION` was exercised once**, on a running instance after
   bootstrap. Its interaction with OIDC sign-in, which upstream reports it also
   disables, was not tested because no OIDC provider is configured.
7. **Mixpost Lite's default admin account.** The harness records only that the
   account exists (`ships_default_admin_account`); it never attempts the login.
   That the documented default password authenticates on a fresh instance is a
   manual observation made during exploration, not harness evidence, and it
   should be re-verified by hand before being relied on. Whether a later Lite
   release changes this was not tested.
8. **Cold-start timing is one sample per candidate.** Both figures come from a
   laptop container runtime that was also running unrelated stacks, and both
   candidates varied widely between runs — Mixpost Lite answered in about a
   minute on one run and 329 seconds on another with identical inputs. Read the
   numbers as evidence that cold start is slow and contention-sensitive on a
   small host, not as a service-level figure for either product.

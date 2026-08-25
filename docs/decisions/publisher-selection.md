# DG-01 — Self-hosted publisher selection

| Field | Value |
| --- | --- |
| Gate | `DG-01 publisher` (`docs/plans/two-vps-reproducible-implementation-plan.md` §7) |
| Status | **awaiting founder decision** |
| Evidence run | `infra/tests/publisher-eval/run.sh`, 2026-08-25 |
| Blocks | `WP-13` (`publish-1` and the selected publisher adapter), `WP-17` |
| Decision date | _not yet recorded_ |
| Deciding human | _not yet recorded_ |

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
| Postiz | single self-hosted edition | `v2.23.0` | AGPL-3.0-only | $0 | yes |
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
| Verdict | `viable` | `disqualified` |
| Checks passed | 17 / 17 | 2 / 17 |
| Checks failed | 0 | 2 |
| Checks unsupported | 0 | 13 |
| Drills passed | 2 / 2 | 2 / 2 |
| Tenant model | organization | none |
| Machine API | `/public/v1`, `Authorization: <key>` | none |
| Cold start to first API answer | 59 s | 329 s |
| Peak RAM (whole topology) | 2,616 MiB | 755 MiB |
| Steady disk (images + volumes) | 5,474 MiB | 1,887 MiB |

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
image ships a pre-created `admin@example.com` account whose documented default
password authenticates on first boot, and nothing forces a change.

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
3. **Cross-tenant delete answers 500, not 403.** The post correctly survives,
   so the boundary holds, but the error path is wrong. n8n must treat a 500
   from a delete as *indeterminate* and re-read state, never as *deleted*.
4. **Upstream ships no backup documentation.** The dump/restore procedure is
   ours. Temporal's own database and Elasticsearch index are rebuildable state
   and must be excluded from the restore expectation deliberately, not by
   accident.
5. **The upstream Compose file is not deployable as-is.** It pins `:latest`,
   publishes database ports, and ships pgAdmin, Sentry Spotlight, Temporal UI
   and `temporal-admin-tools`. None of those may reach `publish-1`.
6. **Cold start is slow and highly variable.** On a quiet machine the backend
   answered 59 seconds after the converge command. On a machine also running
   unrelated containers, two separate runs never answered inside a ten-minute
   budget and were abandoned. Six containers, a JVM, and Prisma
   migrations do not degrade gracefully when memory and I/O are contended, and
   `publish-1` is a 6 GB host that will also run monitoring and restic. Restart
   time is therefore a real operational property: the restart window,
   health-check grace periods, and any update-rollback drill must budget
   minutes and tolerate a much worse tail. This is the single most likely
   surprise during `WP-13`.
7. **AGPL-3.0.** Self-hosting for the founder's own brands is unrestricted.
   If a modified Postiz were ever exposed over a network to third parties,
   §13 would require offering the corresponding source. Running it unmodified
   for our own brands does not trigger that.

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
| State of record | one PostgreSQL database plus an uploads volume or R2 bucket | one MySQL database plus a storage volume |
| Export | `pg_dump`, drilled in this evaluation | `mysqldump --no-tablespaces`, drilled in this evaluation |
| Rebuildable state | Temporal's PostgreSQL and Elasticsearch index | Redis queue |
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
capability, not on cost or weight. Buying into Mixpost Pro or Enterprise would
spend one to four years of the platform's entire marginal budget to obtain a
capability Postiz already provides for free — and the Mixpost documentation
places "one user owning several workspaces" under the **Enterprise** console,
so $299 is not established as sufficient.

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
6. Back up the Postiz database and uploads. Exclude Temporal's database and
   the Elasticsearch index from the restore expectation, and say so in the
   restore runbook.
7. Budget minutes, not seconds, for a `publish-1` publisher restart. Set the
   health-check grace period and the update-rollback drill's timeout from a
   measured cold start on the real host, not from this evaluation's figure.

## Founder decision

> _An agent must not fill this in._

- Selected publisher and exact edition: _pending_
- Date: _pending_
- Notes and any condition the founder attaches: _pending_

Recording a selection here closes `DG-01` and unblocks `WP-13`. Until then no
publisher role, Compose project, or adapter may be committed.

## Limitations

Everything this evidence does **not** cover:

1. **Architecture.** Measured on `linux/arm64` under a shared local container
   runtime, not on an x86-64 VPSDime Linux6GB host. Memory figures are a
   short-run bound on the same images, not a host measurement.
2. **Duration.** Roughly one minute of sampling per candidate, not the
   seven-day `WP-13` canary. The peak figure bounds convergence and the
   fixture matrix; it does not bound a week of scheduled work, media uploads,
   or a Postiz upgrade.
3. **No real provider.** Channels are database fixtures. Token refresh,
   provider rate limits, media upload to a provider, duplicate-post protection
   against a live account, and OAuth grant behaviour are all untested here.
4. **Paid Mixpost editions are entirely untested.** Their workspace isolation,
   API authorization, footprint and restore behaviour are vendor claims.
5. **Postiz upgrade rollback is untested.** The evaluation converges one
   version; it does not upgrade `v2.22.1` to `v2.23.0` and roll back.
6. **`DISABLE_REGISTRATION` was exercised once**, on a running instance after
   bootstrap. Its interaction with OIDC sign-in, which upstream reports it also
   disables, was not tested because no OIDC provider is configured.
7. **Mixpost Lite's default admin account** was confirmed to authenticate on a
   fresh instance. Whether a later Lite release changes this was not tested.
8. **Cold-start timing is one sample per candidate.** Both figures come from a
   laptop container runtime that was also running unrelated stacks, and both
   candidates varied widely between runs — Mixpost Lite answered in about a
   minute on one run and 329 seconds on another with identical inputs. Read the
   numbers as evidence that cold start is slow and contention-sensitive on a
   small host, not as a service-level figure for either product.

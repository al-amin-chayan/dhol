# claude/dg01-publisher-selection

Agent: claude

Head: recorded in the PR's review-request comment

Issue: #16 — `[10/27][DG-01] Select the self-hosted publisher and record the
founder decision`. The founder selected **Postiz** on 2026-08-25 after reading
the packet, so the selection is now recorded in this branch and the PR closes
the issue.

## What changed

- New disposable evaluation harness under `infra/tests/publisher-eval/`:
  digest-pinned candidate list, two Compose topologies, a seventeen-check
  fixture matrix, a capacity summariser, a mechanical verdict, and unit tests.
- New decision-record convention (`docs/decisions/README.md`) and the DG-01
  packet (`docs/decisions/publisher-selection.md`).
- New runbook `docs/runbooks/publisher-evaluation.md`.
- `scripts/check` now shellchecks the harness and runs its tests.
- `README.md` §9 points at the packet and §10 records the evidence run. The
  DG-01 checkbox stays **unchecked**.

## Why

`WP-13` cannot start until DG-01 closes, and the plan forbids inferring the
choice from `README.md`'s "Postiz is the current default" wording. The gate
needed like-for-like measured evidence for the exact $0 editions.

## Verified

Both candidates ran the same matrix on `linux/arm64` through
`infra/tests/publisher-eval/run.sh`. Evidence lands in gitignored
`.artifacts/publisher-eval/<candidate>/<variant>/evidence.json`.

- **Postiz `v2.23.0`** — `viable`. 17/17 checks and both drills passed:
  three separate organizations, per-organization API key, cross-tenant read,
  write, post-read and delete all refused, key rotation invalidates
  immediately, `DISABLE_REGISTRATION` closes signup, `pg_dump` restore
  preserves every organization.
- **Mixpost Lite `v2.6.0`** — `disqualified`. Zero workspace routes and zero
  non-Horizon API routes in the live route table, and a label created by one
  login is returned to another. Its dump/restore drill passes; that does not
  reach the requirement.
- `scripts/check` passes through the pinned controller.
- No plaintext secret is committed. Fixture credentials are generated per run
  into a temporary directory outside the repository, recorded only as
  truncated SHA-256 digests, and the run asserts the generated prefix is
  absent from the evidence before it finishes.

## Assumed / left out

- **The founder decision was recorded, not inferred.** The founder read the
  packet and stated the selection on 2026-08-25; that section is a
  transcription. The harness still cannot emit a `selected` verdict, and it
  was not re-run after the decision because the decision changes no measured
  result.
- Measured on `linux/arm64` under a shared local container runtime, not on an
  x86-64 VPSDime host, and for about a minute per candidate rather than the
  seven-day `WP-13` canary. Both limits are stated in the packet.
- Channels are database fixture rows. No social account, OAuth grant or
  provider call was involved, so token refresh and live duplicate-post
  protection are untested.
- Mixpost Pro and Enterprise were **not** run: their images need a licence key
  and DG-01 authorises no purchase. They are recorded with price and vendor
  claims only.
- No publisher role, Compose project or adapter was committed — `WP-13` stays
  blocked.

## Review focus

1. **Is the evidence honest about what it proves?** Especially: a cross-tenant
   rejection is only counted when the identical request succeeds for the
   tenant's own channel (`probe.py`, `authz.cross-tenant-write-rejected`).
   Check that no other check can pass for the wrong reason.
2. **Redaction.** `probe.py` records credentials only as `digest()` output and
   `run.sh` greps the artifact tree for the run's fixture-password prefix.
   Look for any path that could still print a JWT, API key or password.
3. **The capacity numbers.** `resources.py` sums every container in the
   topology and every image the Compose project pulls. Confirm the budgets
   match `WP-13`'s verify clause and that `min_ram_mib` is not being read as
   an idle figure.
4. **The Elasticsearch finding.** The packet claims Temporal SQL visibility
   makes the Postiz backend fail to start. Reproduce with
   `--variant temporal-sql` per the runbook before accepting it.
5. **The cost table.** It is a complete wallet, not a delta, and it is larger
   than `README.md` §6's marginal figure by design. Check the amortisation of
   the one-time Mixpost prices is presented fairly.
6. **Scope.** The founder's selection is recorded, so confirm the wording
   attributes it to the founder rather than to the evidence, and that nothing
   here pre-commits `WP-13`'s implementation — only unblocks it.

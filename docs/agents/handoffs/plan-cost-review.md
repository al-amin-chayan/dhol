# codex/plan-cost-review

Agent: codex  
Head: 2d738673622f7e27d0f6c0ba77930d854836eb17 (Claude Code round-one reviewed head; fixes require final re-review)

## Cross-review status

Reviewer: Claude Code

Reviewed head: 2d738673622f7e27d0f6c0ba77930d854836eb17

Round-one verdict: two required findings and two suggestions; all four accepted and addressed in this revision.

Merge status: a final Claude Code re-review of the new branch head is still required before merge; the merge commit must record that final reviewed SHA.

## What changed

Added `docs/reviews/ai-social-media-plan-review-2026-08-12.md`, a detailed review of the founding social-media plan covering:

- a plain-language explanation of what Postiz facilitates and what remains in n8n/Telegram/brand profiles;
- tool-by-tool keep/change/option decisions;
- current public prices and a reconciled two-brand cost model;
- official API limits affecting competitor research and publishing;
- a two-brand comparison of native scheduling, Upload-Post, Metricool, self-hosted/hosted Postiz, Mixpost, Buffer, and Zernio;
- a VPSDime plan/add-on comparison identifying the $14 Linux12GB upgrade as the self-hosting sweet spot;
- a read-only live VPS audit covering Paperclip/w3exam RAM, disk, Docker storage, cgroup allocation, health, backup retention, and service exposure;
- a corrected w3exam migration estimate (about 1.36 GB disk and 190 MiB RAM, not 8–10 GB disk);
- diagnosis of Paperclip's failed/nested backup amplification and a restic-owned encrypted R2 recovery redesign that leaves the application unchanged;
- a one-box Paperclip/Hermes/n8n/Postiz/R2 architecture, isolation rules, upgrade checklist, resource thresholds, and $21-tier escalation rules;
- immediate-resize, migration-first, and stay-at-$7 sequences so neither the server move nor Postiz delays either brand;
- complete-cash, marginal-cash, annual-savings, and founder-time break-even views;
- a deterministic Telegram approval gate and metrics model;
- VPS, storage, security, retry, and backup gates;
- a six-week rollout that operates PoriPati and w3exam from the first week, with channel-scope options and exit criteria before increasing cadence.

## Why

The founding plan has a good architecture but relies on several unsafe or incomplete assumptions: projected VPS free disk is below Postiz's documented floor, full commercial competitor research is not available through official TikTok/Meta research APIs, ElevenLabs free output is not commercially licensed, and flat-rate Codex subscription capacity is not a dependable automation budget. The first review also incorrectly recommended postponing w3exam; the revision keeps both brands active and makes publisher/channel scope the adjustable variable instead. Current VPSDime pricing resolves the infrastructure unknown: upgrading the already-paid $7 server to 12 GB RAM/60 GB disk costs $14 total and is cheaper than adding equivalent disk à la carte.

The live audit changed the operational explanation. The server is not currently RAM-constrained and w3exam is small. Disk pressure comes primarily from Paperclip's host wrapper storing 24 already-compressed hourly dumps inside each of seven daily archives while every daily job has exited nonzero since July 28. Resizing without fixing this would only postpone disk exhaustion.

## Verified

- Prices and product rules were checked against vendor documentation on 2026-08-12.
- Postiz's documented 20 GB disk floor, 8 GB RAM recommendation, and Temporal dependency were checked against its current system requirements.
- TikTok and YouTube unaudited/unverified private-publish restrictions were checked against official API documentation.
- Postiz API/draft-status capabilities and hosted 10-/30-channel prices were checked against current Postiz documentation.
- VPSDime's $7, $14, and $21 Linux tiers, $2.50/10 GB storage add-on, $5/core add-on, $5 backup add-on, and live/prorated upgrade behavior were checked against current official plan and knowledge-base pages.
- Read-only SSH measurements found a 6 GiB/nominal-30 GB LXC with no swap, 82% disk use, about 5.0 GiB available RAM, and no point-in-time memory/I/O pressure.
- Paperclip measured about 614 MiB RAM, zero restarts/OOM kills since 2026-05-15, a 3.48 GB image, and 18.25 GB under `/srv/paperclip`; no Paperclip application change was made.
- w3exam measured about 190 MiB RAM and approximately 1.36 GB of reclaimable unique images/volume/source/writable data.
- Paperclip backup inspection found seven daily archives totaling 13.56 GB, 41 hourly dumps totaling 3.55 GB, daily archives rising about 90 MB/day, daily `tar` failures since July 28, and no checksum creation on those failed runs.
- Hermes' official Docker, cron, and security documentation was checked: cron is gateway-driven, script-only cron avoids model use, and its security policy treats OS/container isolation—not in-process approval—as the boundary.
- The installed cloudflared version supports token-file mode; live process arguments currently expose the tunnel token and two daemon processes need owner review/rotation.
- Anthropic's official Sonnet 5 documentation confirms that $2/$10 per million input/output tokens is introductory through 2026-08-31 and $3/$15 is the durable standard rate; the cost model now uses the latter.
- Restic's official documentation confirms policy-based daily/weekly retention, interruption-safe backup/prune behavior, and repository integrity checking; the backup bucket now has restic as its sole retention authority and no R2 expiry lifecycle.
- Postiz v2.23.0's streamed uploads and pending-post duplicate protection were checked against its release notes; open issue #1321 is still treated as a distinct reproduction test, not assumed fixed.
- Upload-Post's two-profile free test, $192/year five-profile Basic plan, supported API platforms, n8n/Make support, and $19/month X-link add-on were checked against current vendor pages.
- Metricool Starter's five-brand $20 annual-equivalent/$25 monthly prices, competitor limit, X add-on, and absence of Starter API/approval access were checked against current vendor documentation.
- Mixpost, Buffer, and Zernio features and current pricing were checked against their official pages.
- Cost arithmetic was reconciled: upgraded-VPS self-hosting is $21–31 complete cash or $14–24 additional from today's $7 state; Upload-Post is $30–40 complete/$23–33 additional; Metricool is $34–44 annual-equivalent or $39–49 monthly; hosted Postiz is $53–63 Team/$63–73 Pro including the existing server and base AI system.
- The $7 upgrade saves $108/year versus Upload-Post; at $20/hour that equals 5.4 hours/year of extra founder operations.
- `git diff --check` passed after the cross-review revision.

## Assumed / left out

- This is a recommendation document only; it does not modify the founding README, buy a subscription, or implement workflows.
- The founder authorized SSH inspection. It was read-only: no service, file, cron job, package, container, tunnel, VPSDime plan, provider app, or account was changed. Hermes, n8n, and Postiz were not installed. Exact prorated checkout cost must be confirmed in the founder's client portal.
- Resource data is a point-in-time audit plus short samples, not a 24-hour/seven-day high-water series. The 10–12 GB post-repair disk projection and 2 GB Hermes/1.5 GB n8n guardrails are explicitly planning estimates to validate, not observed consumption or vendor requirements.
- A diagnostic process listing exposed a truncated prefix of the existing cloudflared credential in the tool transcript. It should be rotated as a precaution even though the displayed value was truncated; the document also recommends token-file mode.
- The Postiz duplicate-post item is explicitly identified as an open user-reported issue; the document requires a reproduction/fix gate rather than asserting every release is affected.
- Tax and foreign-exchange/card fees are outside the cash totals. Founder labor and the already-committed $7 server are shown separately so marginal and complete cash are not confused.

## Review adjudication

1. **Accept — Sonnet 5 pricing.** Replaced the expiring introductory rate as the budget basis with the September standard rate. Sonnet becomes $1.20 and the illustrative subtotal becomes $3.75; the August-only $0.80/$3.35 figures remain clearly labeled, and the $4–8 cap is unchanged.
2. **Accept — stale head reference.** Replaced the stale `Head:` value and recorded Claude Code's round-one reviewed commit explicitly above. Because this feedback produces a new commit, final cross-review must cite the new head before merge rather than falsely treating `2d73867` as coverage of the fixes.
3. **Accept — one backup authority.** Removed the tar/checksum/rename plus R2-lifecycle design. One locked job creates a fresh local dump, sends the dump/config/required data directly to encrypted restic storage, applies `forget --keep-daily 7 --keep-weekly 4 --prune`, runs `check`, and retains at most one non-historical local dump. The private restic bucket has no object-expiry lifecycle.
4. **Accept — Hermes terminology.** n8n is the required deterministic orchestrator. Hermes is a planned isolated resident for opportunistic batch/research work and remains off the approval, publishing, and deadline-critical paths.

## Review focus

- Check whether the Postiz capability description cleanly separates publishing operations from research, brand knowledge, creative production, and the Telegram approval record.
- Check whether the Postiz capacity/reliability checks are proportionate and clearly presented as one option rather than a two-brand launch blocker.
- Verify that the $14 VPSDime recommendation correctly dominates storage add-ons and that the $21 escalation thresholds are conservative but usable.
- Verify the standard-rate Sonnet arithmetic: $1.20 model share, $3.75 illustrative subtotal, unchanged $4–8 cap.
- Recalculate the ~1.36 GB w3exam reclaim estimate and the 10–12 GB post-backup-repair host projection from the documented live measurements.
- Adversarially review the simplified Paperclip recovery path: fresh dump, direct restic backup, restic-owned retention/checking, no backup-bucket lifecycle, and restore-before-delete sequence.
- Check that Hermes can remain useful with no Docker socket/host mounts and that its Telegram role cannot bypass n8n's approval authority.
- Check the cloudflared token-file/one-service recommendation and treat token rotation as required before installing Hermes.
- Recheck complete-versus-marginal cash arithmetic and the 5.4-hour founder-time break-even.
- Check that the R2/media, backup, Docker-log, n8n-pruning, and workload-staggering architecture is operationally sound on 12 GB/60 GB.
- Check that the v2.23.0 duplicate-protection wording does not imply the still-open #1321 failure is proven fixed.
- Recheck the Upload-Post and Metricool two-brand semantics, price breakpoints, API limitations, and X add-ons.
- Recheck all 8-account/14-account cost arithmetic and the publisher-inclusive totals.
- Confirm that both brands are active throughout the rollout and that only channel scope/cadence changes when founder time is constrained.
- Check that recommendations preserve human approval, no AI-avatar testimonials, scripted Bangla text, git reproducibility, and bounded disk usage.
- Flag any claim whose cited source does not directly support it or whose wording overstates an inference.

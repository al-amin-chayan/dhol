# codex/plan-cost-review

Agent: codex  
Head: f899f66

## What changed

Added `docs/reviews/ai-social-media-plan-review-2026-08-12.md`, a detailed review of the founding social-media plan covering:

- a plain-language explanation of what Postiz facilitates and what remains in n8n/Telegram/brand profiles;
- tool-by-tool keep/change/option decisions;
- current public prices and a reconciled two-brand cost model;
- official API limits affecting competitor research and publishing;
- a two-brand comparison of native scheduling, Upload-Post, Metricool, self-hosted/hosted Postiz, Mixpost, Buffer, and Zernio;
- a VPSDime plan/add-on comparison identifying the $14 Linux12GB upgrade as the self-hosting sweet spot;
- a one-box Postiz/R2 architecture, upgrade checklist, resource thresholds, and $21-tier escalation rules;
- complete-cash, marginal-cash, annual-savings, and founder-time break-even views;
- a deterministic Telegram approval gate and metrics model;
- VPS, storage, security, retry, and backup gates;
- a six-week rollout that operates PoriPati and w3exam from the first week, with channel-scope options and exit criteria before increasing cadence.

## Why

The founding plan has a good architecture but relies on several unsafe or incomplete assumptions: projected VPS free disk is below Postiz's documented floor, full commercial competitor research is not available through official TikTok/Meta research APIs, ElevenLabs free output is not commercially licensed, and flat-rate Codex subscription capacity is not a dependable automation budget. The first review also incorrectly recommended postponing w3exam; the revision keeps both brands active and makes publisher/channel scope the adjustable variable instead. Current VPSDime pricing resolves the infrastructure unknown: upgrading the already-paid $7 server to 12 GB RAM/60 GB disk costs $14 total and is cheaper than adding equivalent disk à la carte.

## Verified

- Prices and product rules were checked against vendor documentation on 2026-08-12.
- Postiz's documented 20 GB disk floor, 8 GB RAM recommendation, and Temporal dependency were checked against its current system requirements.
- TikTok and YouTube unaudited/unverified private-publish restrictions were checked against official API documentation.
- Postiz API/draft-status capabilities and hosted 10-/30-channel prices were checked against current Postiz documentation.
- VPSDime's $7, $14, and $21 Linux tiers, $2.50/10 GB storage add-on, $5/core add-on, $5 backup add-on, and live/prorated upgrade behavior were checked against current official plan and knowledge-base pages.
- Postiz v2.23.0's streamed uploads and pending-post duplicate protection were checked against its release notes; open issue #1321 is still treated as a distinct reproduction test, not assumed fixed.
- Upload-Post's two-profile free test, $192/year five-profile Basic plan, supported API platforms, n8n/Make support, and $19/month X-link add-on were checked against current vendor pages.
- Metricool Starter's five-brand $20 annual-equivalent/$25 monthly prices, competitor limit, X add-on, and absence of Starter API/approval access were checked against current vendor documentation.
- Mixpost, Buffer, and Zernio features and current pricing were checked against their official pages.
- Cost arithmetic was reconciled: upgraded-VPS self-hosting is $21–31 complete cash or $14–24 additional from today's $7 state; Upload-Post is $30–40 complete/$23–33 additional; Metricool is $34–44 annual-equivalent or $39–49 monthly; hosted Postiz is $53–63 Team/$63–73 Pro including the existing server and base AI system.
- The $7 upgrade saves $108/year versus Upload-Post; at $20/hour that equals 5.4 hours/year of extra founder operations.
- `git diff --cached --check` passed before VPSDime revision commit `f899f66`.

## Assumed / left out

- This is a recommendation document only; it does not modify the founding README, buy a subscription, or implement workflows.
- No live VPS utilization measurement, VPSDime account access/upgrade, provider app submission, or scheduler installation was authorized or performed. Exact prorated checkout cost must be confirmed in the founder's client portal.
- The Postiz duplicate-post item is explicitly identified as an open user-reported issue; the document requires a reproduction/fix gate rather than asserting every release is affected.
- Tax and foreign-exchange/card fees are outside the cash totals. Founder labor and the already-committed $7 server are shown separately so marginal and complete cash are not confused.

## Review focus

- Check whether the Postiz capability description cleanly separates publishing operations from research, brand knowledge, creative production, and the Telegram approval record.
- Check whether the Postiz capacity/reliability checks are proportionate and clearly presented as one option rather than a two-brand launch blocker.
- Verify that the $14 VPSDime recommendation correctly dominates storage add-ons and that the $21 escalation thresholds are conservative but usable.
- Recheck complete-versus-marginal cash arithmetic and the 5.4-hour founder-time break-even.
- Check that the R2/media, backup, Docker-log, n8n-pruning, and workload-staggering architecture is operationally sound on 12 GB/60 GB.
- Check that the v2.23.0 duplicate-protection wording does not imply the still-open #1321 failure is proven fixed.
- Recheck the Upload-Post and Metricool two-brand semantics, price breakpoints, API limitations, and X add-ons.
- Recheck all 8-account/14-account cost arithmetic and the publisher-inclusive totals.
- Confirm that both brands are active throughout the rollout and that only channel scope/cadence changes when founder time is constrained.
- Check that recommendations preserve human approval, no AI-avatar testimonials, scripted Bangla text, git reproducibility, and bounded disk usage.
- Flag any claim whose cited source does not directly support it or whose wording overstates an inference.

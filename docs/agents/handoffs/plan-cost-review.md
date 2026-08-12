# codex/plan-cost-review

Agent: codex  
Head: 09f7665

## What changed

Added `docs/reviews/ai-social-media-plan-review-2026-08-12.md`, a detailed review of the founding social-media plan covering:

- a plain-language explanation of what Postiz facilitates and what remains in n8n/Telegram/brand profiles;
- tool-by-tool keep/change/option decisions;
- current public prices and a reconciled two-brand cost model;
- official API limits affecting competitor research and publishing;
- a two-brand comparison of native scheduling, Upload-Post, Metricool, self-hosted/hosted Postiz, Mixpost, Buffer, and Zernio;
- a deterministic Telegram approval gate and metrics model;
- VPS, storage, security, retry, and backup gates;
- a six-week rollout that operates PoriPati and w3exam from the first week, with channel-scope options and exit criteria before increasing cadence.

## Why

The founding plan has a good architecture but relies on several unsafe or incomplete assumptions: projected VPS free disk is below Postiz's documented floor, full commercial competitor research is not available through official TikTok/Meta research APIs, ElevenLabs free output is not commercially licensed, and flat-rate Codex subscription capacity is not a dependable automation budget. The first review also incorrectly recommended postponing w3exam; the revision keeps both brands active and makes publisher/channel scope the adjustable variable instead.

## Verified

- Prices and product rules were checked against vendor documentation on 2026-08-12.
- Postiz's documented 20 GB disk floor, 8 GB RAM recommendation, and Temporal dependency were checked against its current system requirements.
- TikTok and YouTube unaudited/unverified private-publish restrictions were checked against official API documentation.
- Postiz API/draft-status capabilities and hosted 10-/30-channel prices were checked against current Postiz documentation.
- Upload-Post's two-profile free test, $192/year five-profile Basic plan, supported API platforms, n8n/Make support, and $19/month X-link add-on were checked against current vendor pages.
- Metricool Starter's five-brand $20 annual-equivalent/$25 monthly prices, competitor limit, X add-on, and absence of Starter API/approval access were checked against current vendor documentation.
- Mixpost, Buffer, and Zernio features and current pricing were checked against their official pages.
- Cost arithmetic was reconciled: base two-brand system $7–17/month; with publisher, native $7–17, Upload-Post $23–33, Metricool $27–37 annual-equivalent/$32–42 monthly, hosted Postiz $46–56 for 8 accounts or $56–66 for 14, excluding optional voice/X and tax.
- `git diff --cached --check` passed before revision commit `09f7665`.

## Assumed / left out

- This is a recommendation document only; it does not modify the founding README, buy a subscription, or implement workflows.
- No live VPS utilization measurement, provider app submission, or scheduler installation was authorized or performed.
- The Postiz duplicate-post item is explicitly identified as an open user-reported issue; the document requires a reproduction/fix gate rather than asserting every release is affected.
- Tax, foreign-exchange/card fees, founder labor, committed subscription costs, and an unknown VPS upgrade quote are intentionally outside the cash totals and are called out separately.

## Review focus

- Check whether the Postiz capability description cleanly separates publishing operations from research, brand knowledge, creative production, and the Telegram approval record.
- Check whether the Postiz capacity/reliability checks are proportionate and clearly presented as one option rather than a two-brand launch blocker.
- Recheck the Upload-Post and Metricool two-brand semantics, price breakpoints, API limitations, and X add-ons.
- Recheck all 8-account/14-account cost arithmetic and the publisher-inclusive totals.
- Confirm that both brands are active throughout the rollout and that only channel scope/cadence changes when founder time is constrained.
- Check that recommendations preserve human approval, no AI-avatar testimonials, scripted Bangla text, git reproducibility, and bounded disk usage.
- Flag any claim whose cited source does not directly support it or whose wording overstates an inference.

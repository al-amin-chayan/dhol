# codex/plan-cost-review

Agent: codex  
Head: a20b517

## What changed

Added `docs/reviews/ai-social-media-plan-review-2026-08-12.md`, a detailed review of the founding social-media plan covering:

- tool-by-tool keep/change/defer decisions;
- current public prices and a reconciled two-brand cost model;
- official API limits affecting competitor research and publishing;
- Postiz/Mixpost/managed/native-scheduling tradeoffs;
- a deterministic Telegram approval gate and metrics model;
- VPS, storage, security, retry, and backup gates;
- a six-week one-brand rollout with exit criteria.

## Why

The founding plan has a good architecture but relies on several unsafe or incomplete assumptions: projected VPS free disk is below Postiz's documented floor, full commercial competitor research is not available through official TikTok/Meta research APIs, ElevenLabs free output is not commercially licensed, and flat-rate Codex subscription capacity is not a dependable automation budget.

## Verified

- Prices and product rules were checked against vendor documentation on 2026-08-12.
- Postiz's documented 20 GB disk floor, 8 GB RAM recommendation, and Temporal dependency were checked against its current system requirements.
- TikTok and YouTube unaudited/unverified private-publish restrictions were checked against official API documentation.
- Claude token/search pricing, Gemini image output pricing, ElevenLabs commercial tier, R2 free tier, X billing model, hosted Postiz tiers, and Mixpost tiers were checked against current vendor pages.
- Cost arithmetic was reconciled: lean two-brand $7–17/month; $15–33 with ElevenLabs and X enabled for both, excluding any VPS upgrade.
- `git diff --cached --check` passed before the content commit.

## Assumed / left out

- This is a recommendation document only; it does not modify the founding README or implement workflows.
- No live VPS utilization measurement, provider app submission, or scheduler installation was authorized or performed.
- The Postiz duplicate-post item is explicitly identified as an open user-reported issue; the document requires a reproduction/fix gate rather than asserting every release is affected.
- Tax, foreign-exchange/card fees, founder labor, committed subscription costs, and an unknown VPS upgrade quote are intentionally outside the cash totals and are called out separately.

## Review focus

- Check whether the Postiz capacity/reliability gates are proportionate to the README's 30 GB shared VPS constraint.
- Recheck cost assumptions and the $7–17 / $15–33 arithmetic.
- Check that recommendations preserve human approval, no AI-avatar testimonials, scripted Bangla text, git reproducibility, and bounded disk usage.
- Flag any claim whose cited source does not directly support it or whose wording overstates an inference.

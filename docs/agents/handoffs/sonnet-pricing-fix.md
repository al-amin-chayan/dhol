# claude/sonnet-pricing-fix

Agent: claude

## What changed

Corrected the Claude Sonnet 5 pricing claim in
`docs/reviews/ai-social-media-plan-review-2026-08-12.md` (two passages: the
Claude API row of the tool-choice table, and the revised-cost-model LLM
workload calculation).

The document (as merged from `codex/plan-cost-review`) budgeted on the claim
that Sonnet 5's $2/$10 per-MTok rate is introductory through 2026-08-31 with a
"durable" $3/$15 standard rate from September. Anthropic's canonical pricing
page now states the opposite: the launch-introductory $2/$10 rate has been made
the standard price and the scheduled 2026-09-01 increase to $3/$15 will not
occur.

Corrected figures: Sonnet line `(0.2 × $2) + (0.04 × $10) = $0.80`,
illustrative LLM subtotal **$3.35**. The cancelled-increase counterfactual
($3.75) is retained as one sentence to show the $4–8 cap was robust either
way. Citations now point at the pricing page's model-pricing section, which
contains the explicit introductory-pricing note; the previous
`whats-new-sonnet-5#pricing` citation was removed because that page never
stated an introductory expiry.

## Why

Cross-review round two of PR #1 found the claim contradicted by the live
source of truth. The error originated in Claude Code's own round-one feedback
(based on a June-cached reference that predated Anthropic's cancellation), so
per founder decision PR #1 merged as-is and this lane carries the correction.

## Verified

- The pricing page note was fetched 2026-08-13:
  "The $2/$10 per million input/output token pricing for Claude Sonnet 5,
  announced at launch as introductory pricing through August 31, 2026, is now
  the standard price. The previously scheduled increase to $3/$15 ... will not
  occur."
- Haiku 4.5 $1/$5, web search $10 per 1,000, and the 50% batch discount were
  re-confirmed on the same page.
- Arithmetic recomputed: $1.55 + $0.80 + $1.00 = $3.35.
- No other passage in the document still asserts the September increase
  (`grep` for `3.75`, `1.20`, `introductory`, `whats-new-sonnet-5`).

## Assumed / left out

- Out of scope per founder: the second round-two `required` finding — the
  restic redesign's backup-job cadence and intra-day recovery granularity
  (single latest local dump vs the old 24-hourly window) is still implicit.
  One sentence stating the cadence/RPO, or `--keep-hourly 24` in the restic
  policy, resolves it. Left for a future lane.

## Review focus

- Confirm the pricing-page note says what this handoff quotes.
- Confirm both edited passages agree with each other and with the $4–8 cap.
- Confirm no stale $3/$15-as-standard or September-increase language remains.

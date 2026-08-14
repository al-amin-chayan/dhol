# Dholbeat — Multi-Brand Social Growth Platform

> **Dholbeat** (ঢোল — the drum; "ঢোল পেটানো" = to publicize — fused with the
> steady posting beat). Product/marketing domain **dholbeat.com** and GitHub
> handle `dholbeat` verified available 2026-08-12 — register both before
> establishing the public product identity. Operational interfaces use
> `chayan.me` subdomains under the policy in §5.

> Living document and founding plan of this repository. Extracted on
> 2026-08-12 from the PoriPati repo's growth planning (Track 2 of
> `docs/growth/AI_GROWTH_ENGINE_PLAN.md`); Dholbeat is deliberately
> independent of any client project — PoriPati and w3exam consume it as
> brand profiles.

| Field | Value |
| --- | --- |
| Owner | Chayan |
| Last updated | 2026-08-13 |
| Status | Draft — extracted from the PoriPati AI growth engine plan (Track 2) |
| Brands (initial) | **PoriPati** (salon/beauty marketplace, BD) · **w3exam** (exam-prep) |
| Hosting | Two VPSDime Linux6GB services in one account — decided 2026-08-13 |
| Budget | Shares the founder's ≤$75/mo growth ceiling; platform's own marginal cost ≈ $10–25/mo |

> **Working in this repo?** Read `AGENTS.md` first (auto-loads in Claude Code
> and Codex sessions), and run `scripts/lanes.sh` before starting a task —
> both agents work here in parallel on isolated worktree lanes.

## 1. Objective

One self-hosted, multi-brand platform that keeps every project's social
channels alive with researched, drafted, approved, and scheduled content —
run by AI, steered by a solo founder in ~1–2 hours per brand per week.
No per-project rebuild: adding a brand = adding a **brand profile**, not code.

## 2. Design principles

- **Brand-agnostic core.** All brand knowledge lives in per-brand profile
  config (accounts, language mix, tone, niche, visual tokens, posting
  windows). The pipelines never hard-code a brand.
- **Isolated from client products.** No dependency on any client project's
  code, DB, or infra. Clients interact only through their brand profile,
  their Telegram approval channel, and (optionally) webhooks.
- **Free/self-hosted first.** Open-source stack on owned infra; paid APIs
  only where they demonstrably win (image gen, X posting).
- **Reproducible from git** (founder's laptop-loss rule): compose stack,
  n8n flow exports (JSON), brand profiles, prompts — all committed.
  Local media is ephemeral: purge after publish (or push to B2).
- **No plaintext secrets in git.** SOPS+age-encrypted `*.sops.yml` values may
  be committed only under the repository's `.sops.yaml` policy with CI
  verification. Age private keys and provider recovery logins stay in the
  password manager; `.env` files are never committed.
- **Human approval gate.** Nothing publishes without founder approval in
  the brand's Telegram channel. AI-content disclosure rules honoured
  (see §8 research).

## 3. Components

| Component | Role | Tool |
| --- | --- | --- |
| **Social Media Researcher** | Weekly per-brand: niche trend scan, competitor pages, own-post engagement analytics → audience-interest analysis → next week's suggested content calendar | n8n scheduled flow + LLM (Claude API; Hermes cron as the ~$0 batch alternative) |
| **Content Studio** | Turns approved ideas into drafts: bilingual captions, images (AI background + manual/scripted text overlay), short vertical videos | Claude API · Nano Banana 2 / Flux (fal.ai) · Canva free (Bangla/Latin text overlay) · CapCut + stock B-roll + ElevenLabs voiceover |
| **Approval queue** | Per-brand Telegram channel: idea approval (weekly batch) + final draft approval | Telegram Bot API (or Hermes Telegram gateway) |
| **Publisher** | Scheduled cross-posting to all brand channels | **Postiz** self-hosted by default (one workspace per brand), or Mixpost if the open comparison selects it · Telegram Bot API (channels) · X API pay-per-use |
| **Metrics loop** | Pull engagement per post; feeds the next researcher run | Platform insights APIs via n8n |

## 4. Brand profile (the extension point)

```yaml
brand: poripati            # or w3exam, or any future project
languages: [bn, en]        # bn-first for poripati
niche: "salon & beauty services, Bangladesh"
tone: "warm, trustworthy, local"
channels:                  # Postiz workspace mapping
  facebook: PoriPatiApp
  instagram: poripati.app
  tiktok: poripati92
  youtube: PoriPatiApp     # Shorts via normal ≤60s upload
  telegram: @poripati
  x: PoriPati              # pay-per-use API
  threads: poripati.app    # via Postiz
  bluesky: poripati.app
cadence: {reels: 3/wk, static: 1-2/wk}
approval_channel: telegram:<chat-id>
visual: {palette: ..., logo: ..., fonts: ...}
no_go: ["AI avatar testimonials", "medical claims", ...]
```

## 5. Hosting & operations (decided 2026-08-13)

The founder approved **two independent VPSDime Linux6GB services under the
existing customer account**, at $7/month each ($14/month total):

| Host | Workloads | Operating boundary |
| --- | --- | --- |
| `core-1` | Paperclip, n8n, bounded Hermes worker, monitoring, restic | Paperclip becomes reproducible from Git under a strict before/after configuration-parity guard. A planned container recreation is allowed; its image digest and effective configuration must not change during adoption. |
| `publish-1` | The selected publisher stack, monitoring, restic | Postiz is the current default but the Postiz-vs-Mixpost decision remains open. The publisher and its state stay isolated from Paperclip. |

These hosts are not a cluster and cannot pool their RAM or disk. The benefit is
two four-vCPU scheduling envelopes and two failure domains. Public traffic uses
separate Cloudflare tunnels; backups use separate encrypted restic repositories
in private R2. The 6GB/30GB publisher is a measured canary below Postiz's
recommended 8GB/50GB sizing, with an evidence-based publisher-only upgrade
path. The detailed and current infrastructure source of truth is the
[two-VPS infrastructure-as-code plan](docs/plans/two-vps-infrastructure-as-code.md).

`chayan.me` is the operations/admin namespace for both hosts, and Paperclip
keeps its existing `team.chayan.me` hostname. The detailed rules for human
interfaces and machine-only routes are authoritative in the plan's
[public namespace and Zero Trust policy](docs/plans/two-vps-infrastructure-as-code.md#public-namespace-and-zero-trust-policy).
`dholbeat.com` remains the separate product/marketing domain decision in §9.

**Hermes Agent** is a planned, noncritical resident of `core-1`: useful for
bounded research and drafting batches, but never required for an approval or
publishing deadline. n8n remains the deterministic workflow authority, with a
metered API fallback rather than a flat-rate Codex subscription as the
production cost baseline.

## 6. Costs (platform marginal, verified Aug 2026)

| Item | Est./mo |
| --- | --- |
| n8n, selected publisher, Chat approval bot (self-hosted software) | $0 |
| LLM (Claude API; less if Hermes batch absorbs it) | $3–8 |
| Image gen (Nano Banana 2 / Flux) | $5–10 per active brand |
| Video (CapCut + stock + ElevenLabs DIY) | $0 (paid gen only for proven formats: Hailuo $0.19–0.56/clip, Kling $6.99/mo) |
| X API (pay-per-use, ~4 posts/wk) | $2–3 per brand using X |
| **Total (two brands)** | **≈ $10–25** |

The approved second $7 host keeps the initial VPS bill at $14, the
same as the earlier single-Linux12GB recommendation. From today's already-paid
$7 host, the new host plus the $7–17 generation/storage baseline is an
additional **$14–24/month**, within the $10–25 marginal target. If measured
publisher pressure requires upgrading only `publish-1` to $14, additional cash
becomes **$21–31/month** and total cash becomes **$28–38/month**; that escalation
requires a fresh founder cost decision. See the linked IaC plan for thresholds.

## 7. Phases

1. **Infrastructure as code:** capture and parity-adopt Paperclip on `core-1`,
   repair/restore-test backups, then deploy isolated n8n and bounded Hermes.
   Bootstrap founder-approved `publish-1` from the same repository and deploy
   the selected Postiz or Mixpost stack after the open tool decision closes.
2. **Pipeline v1 (both brands):** create separate PoriPati and w3exam profiles,
   evidence queues, approval states, publisher workspaces, and metric views.
   Start with two core ideas for each brand per week and stagger channels—not
   brands—if founder attention is tight.
3. **Prove the extension point:** run both brands without hard-coded brand
   logic; adding any later brand is a profile and workspace change, not code.
4. **Metrics loop:** engagement pulled per post; researcher uses it.
5. **Extract to own repo** as the project package; this file becomes its
   founding README/plan.

## 8. Research findings (from the 2026-08-09 research pass, report A)

- **BD platform reality:** Facebook 64.0M users + TikTok 56.2M adults
  (47.9% of adults) — a dual-platform market; Instagram 9.15M; Threads/X
  negligible (DataReportal Digital 2026 BD). → video-first, FB + TikTok +
  Shorts + IG as first-class, rest cross-posts.
- **Cadence:** 3 solid reels/week beats daily mediocrity; consistency over
  volume.
- **Bangla text-in-image is unsolved** by every image model (Ideogram's
  ~95% text accuracy is Latin-only) → always overlay Bangla text as a
  separate step (Canva / HTML-to-image).
- **Magnific** = image upscaler only ($39/mo min) — not a generator, skip.
- **Scheduling APIs (2026):** Meta Business Suite free but FB+IG only (no
  Threads); Postiz covers 30+ incl. TikTok/Threads/Bluesky; YouTube Shorts
  = normal ≤60s upload; TikTok Content Posting API needs app review;
  X free API tier dead since Feb 2026 (pay-per-use ~$0.015/post);
  Telegram Bot API free; **WhatsApp Channel has no official posting API**
  — manual only (unofficial APIs risk the business number).
- **AI disclosure (2026):** Meta ads AI-label mandatory since Mar 2026;
  TikTok AIGC label for synthetic faces/voices (C2PA auto-detect);
  YouTube self-label for realistic synthetic content. **No AI-avatar
  testimonials, ever** — trust-fatal for marketplace brands.
- **All-in-one social SaaS rejected on cost** (Sprout $99/mo, Brand24
  $79/mo, AI SDR tools $500+).

## 9. Open decisions

- [x] ~~Project/package name~~ → **Dholbeat** / dholbeat.com (2026-08-12)
- [x] ~~Repo location~~ → this repository (`~/Projects/dholbeat`, seeded
      2026-08-12); push to GitHub `dholbeat` when created
- [ ] Register dholbeat.com for the product/marketing identity (availability
      confirmed 2026-08-12 — act soon); operational/admin hostnames under
      `chayan.me` do not close this decision
- [ ] Create the GitHub repo + remote (handle `dholbeat` free as of 2026-08-12)
- [x] ~~Hosting topology~~ → **two $7/month VPSDime Linux6GB services under
      the existing account**, founder-approved 2026-08-13; purchase and manage
      `publish-1` through the detailed IaC plan
- [ ] Postiz vs Mixpost final call (Postiz default: AGPL, 30+ platforms)
- [ ] Approval bot: custom Telegram bot vs Hermes gateway
- [ ] Per-brand X usage (worth $2–3/mo per brand?)
- [ ] Media archival: purge-only vs B2 push

## 10. Change log

| Date | Change |
| --- | --- |
| 2026-08-12 | Extracted from PoriPati AI_GROWTH_ENGINE_PLAN.md (Track 2) as a standalone project seed: brand-profile model, VPSDime hosting, Hermes batch roles, costs, phases |
| 2026-08-12 | Named **Dholbeat** (dholbeat.com + GitHub handle verified available); seeded as this repository's README/plan; scope removed from the PoriPati repo |
| 2026-08-12 | Repo configured for parallel Claude Code + Codex work: `AGENTS.md` (+ `CLAUDE.md` symlink), per-agent worktree lanes (`scripts/new-worktree.sh` / `rm-worktree.sh` / `lanes.sh`), cross-review + handoff protocol (`docs/agents/parallel-work.md`), skeleton `brands/ stack/ n8n/ prompts/` |
| 2026-08-13 | Founder approved two $7/month Linux6GB VPSDime services in the existing account: `core-1` for Paperclip/n8n/Hermes and `publish-1` for the selected publisher. The [IaC plan](docs/plans/two-vps-infrastructure-as-code.md) supersedes the earlier single-host topology and adopts SOPS+age secrets plus Paperclip configuration-parity convergence. |
| 2026-08-13 | Reserved `chayan.me` as the two-VPS operations/admin namespace, preserved Paperclip at `team.chayan.me`, and required Cloudflare Tunnel plus default-deny Cloudflare Zero Trust Access for every human-facing interface; `dholbeat.com` remains the product/marketing domain decision. |

# Dholbeat — Multi-Brand Social Growth Platform

> **Dholbeat** (ঢোল — the drum; "ঢোল পেটানো" = to publicize — fused with the
> steady posting beat). Domain **dholbeat.com** and GitHub handle `dholbeat`
> verified available 2026-08-12 — register both before building anything
> public.

> Living document and founding plan of this repository. Extracted on
> 2026-08-12 from the PoriPati repo's growth planning (Track 2 of
> `docs/growth/AI_GROWTH_ENGINE_PLAN.md`); Dholbeat is deliberately
> independent of any client project — PoriPati and w3exam consume it as
> brand profiles.

| Field | Value |
| --- | --- |
| Owner | Chayan |
| Last updated | 2026-08-12 |
| Status | Draft — extracted from the PoriPati AI growth engine plan (Track 2) |
| Brands (initial) | **PoriPati** (salon/beauty marketplace, BD) · **w3exam** (exam-prep) |
| Hosting | VPSDime box (Dallas) — decided 2026-08-12 |
| Budget | Shares the founder's ≤$75/mo growth ceiling; platform's own marginal cost ≈ $10–25/mo |

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
- **Human approval gate.** Nothing publishes without founder approval in
  the brand's Telegram channel. AI-content disclosure rules honoured
  (see §8 research).

## 3. Components

| Component | Role | Tool |
| --- | --- | --- |
| **Social Media Researcher** | Weekly per-brand: niche trend scan, competitor pages, own-post engagement analytics → audience-interest analysis → next week's suggested content calendar | n8n scheduled flow + LLM (Claude API; Hermes cron as the ~$0 batch alternative) |
| **Content Studio** | Turns approved ideas into drafts: bilingual captions, images (AI background + manual/scripted text overlay), short vertical videos | Claude API · Nano Banana 2 / Flux (fal.ai) · Canva free (Bangla/Latin text overlay) · CapCut + stock B-roll + ElevenLabs voiceover |
| **Approval queue** | Per-brand Telegram channel: idea approval (weekly batch) + final draft approval | Telegram Bot API (or Hermes Telegram gateway) |
| **Publisher** | Scheduled cross-posting to all brand channels | **Postiz** self-hosted (one workspace per brand) · Telegram Bot API (channels) · X API pay-per-use |
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

## 5. Hosting & operations (decided 2026-08-12)

**VPSDime box** (Dallas, 4 vCPU LXC, 6GB RAM, 30GB disk; already runs
paperclip; w3exam migrating off):

- RAM/CPU: comfortable — full stack (n8n ~300MB, Postiz + postgres/redis
  ~1GB, Hermes gateway ~0.5GB) ≈ 2GB; host is oversold but nothing here is
  latency-critical.
- Public HTTPS: existing cloudflared tunnels → Postiz UI behind Cloudflare
  Access; webhook endpoints as needed.
- **Binding constraint: disk** (80% full at decision time). Conditions:
  deploy after w3exam migration + `docker system prune` (expect ~8–10GB
  free); disk alert at 85%; media ephemeral; VPSDime storage add-on only
  when actually forced.
- Isolation from the PoriPati Hetzner fleet is physical.

**Hermes Agent** (founder's install: GPT-5.5 via flat-rate Codex sub) runs
here as the cheap batch worker (researcher sweeps, drafting runs via
`hermes cron`) and Telegram-gateway candidate. Verify Codex fair-use before
moving all batch load onto it.

## 6. Costs (platform marginal, verified Aug 2026)

| Item | Est./mo |
| --- | --- |
| n8n, Postiz, Chat approval bot (self-hosted) | $0 |
| LLM (Claude API; less if Hermes batch absorbs it) | $3–8 |
| Image gen (Nano Banana 2 / Flux) | $5–10 per active brand |
| Video (CapCut + stock + ElevenLabs DIY) | $0 (paid gen only for proven formats: Hailuo $0.19–0.56/clip, Kling $6.99/mo) |
| X API (pay-per-use, ~4 posts/wk) | $2–3 per brand using X |
| **Total (two brands)** | **≈ $10–25** |

## 7. Phases

1. **Stack up** (post-w3exam migration): compose stack (n8n + Postiz +
   postgres/redis) on VPSDime; connect PoriPati brand channels to Postiz;
   Telegram approval bot.
2. **Pipeline v1 (PoriPati brand):** researcher flow → weekly idea batch →
   founder approval → draft generation → approval → scheduled publish.
   Target cadence: 3 reels + 1–2 statics/week.
3. **Second brand (w3exam):** add brand profile + workspace; prove the
   brand-agnostic claim (zero code changes).
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
- [ ] Register dholbeat.com (availability confirmed 2026-08-12 — act soon)
- [ ] Create the GitHub repo + remote (handle `dholbeat` free as of 2026-08-12)
- [ ] Postiz vs Mixpost final call (Postiz default: AGPL, 30+ platforms)
- [ ] Approval bot: custom Telegram bot vs Hermes gateway
- [ ] Per-brand X usage (worth $2–3/mo per brand?)
- [ ] Media archival: purge-only vs B2 push

## 10. Change log

| Date | Change |
| --- | --- |
| 2026-08-12 | Extracted from PoriPati AI_GROWTH_ENGINE_PLAN.md (Track 2) as a standalone project seed: brand-profile model, VPSDime hosting, Hermes batch roles, costs, phases |
| 2026-08-12 | Named **Dholbeat** (dholbeat.com + GitHub handle verified available); seeded as this repository's README/plan; scope removed from the PoriPati repo |

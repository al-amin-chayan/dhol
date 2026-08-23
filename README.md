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
| Last updated | 2026-08-14 |
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
- **Product boundaries survive shared infrastructure.** Dholbeat's social
  pipelines have no dependency on a client project's code, DB, or infra. The
  tools on the two hosts are multi-project-ready where the tool can support it:
  central n8n uses registered consumer manifests, Hermes uses a separately
  managed same-image container, verified `/opt/data`/state backend, workspace
  and credentials for each project, and the publisher uses separate project
  organizations/workspaces and brand account mappings. PoriPati Track-1 is the
  first external automation consumer; w3exam and later
  founder-owned projects can join through the same contracts. Implementations
  remain canonical at exact reviewed commits in their owning repositories and
  reach products only through narrow authenticated HTTPS APIs. Paperclip,
  product databases and product container networks are not shared tenant
  surfaces.
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
| **Approval queue** | Per-brand Telegram channel: idea approval (weekly batch) + final draft approval | Telegram Bot API (or a project-scoped Hermes Telegram profile) |
| **Publisher** | Scheduled cross-posting to all brand channels | **Postiz** self-hosted by default (separate organization per project and account mapping per brand), or Mixpost only if the open comparison proves equivalent $0 separation · Telegram Bot API (channels) · X API pay-per-use |
| **Metrics loop** | Pull engagement per post; feeds the next researcher run | Platform insights APIs via n8n |

## 4. Brand profile (the extension point)

```yaml
schema_version: 1
project_id: poripati      # owner for approvals, credentials, and workflow/project scope
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
approval_channel: telegram:DHOLBEAT_PORIPATI_APPROVAL_CHANNEL
visual: {palette: ..., logo: ..., fonts: ...}
no_go: ["AI avatar testimonials", "medical claims", ...]
```

## 5. Hosting & operations (decided 2026-08-13)

The founder approved **two independent VPSDime Linux6GB services under the
existing customer account**, at $7/month each ($14/month total):

| Host | Workloads | Operating boundary |
| --- | --- | --- |
| `core-1` | Paperclip, central n8n, per-project-container and globally bounded Hermes, monitoring, restic | Paperclip becomes reproducible from Git under a strict before/after configuration-parity guard. n8n and Hermes can serve registered founder-owned projects through separate manifests, credentials, source pins and verified state/workspace boundaries; their shared host and runtime limits remain explicit. |
| `publish-1` | The selected multi-project publisher stack, monitoring, restic | Postiz is the current default but the Postiz-vs-Mixpost decision remains open. Each project receives a separate organization/workspace and brand connection mapping; the publisher and its state stay isolated from Paperclip. |

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

**Hermes Agent** is a planned, noncritical resident of `core-1`. One pinned
image/version serves multiple registered projects, but each project runs in its
own container/service with a unique `/opt/data` mount, local state backend,
workspace, approved skills, schedules and credentials. Activation fails if the
resolved state store is shared; Hermes' native session-key namespacing alone is
not treated as isolation. The initial host-wide Hermes envelope is
approximately 2 GB with only one active agent job across all containers, so
this is a reusable capability rather than an unlimited capacity promise. A
future w3exam profile is a manifest, scoped secret set and reviewed source
pin—not another Hermes code installation. No Hermes profile is required for an
approval or publishing deadline; n8n remains the deterministic workflow
authority, with a metered API fallback rather than a flat-rate Codex
subscription as the production cost baseline.

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
   repair/restore-test backups, then deploy central n8n and Hermes with generic
   project-registration contracts, separate credentials/state and global
   resource bounds. Register PoriPati Track-1 as the first external n8n
   consumer and prove a second credential-free project fixture so w3exam or a
   later project can onboard without another runtime, hard-coded project logic
   or public administration interface.
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
- [x] ~~Central automation ownership~~ → founder-approved 2026-08-14: the
      Dholbeat-managed n8n on `core-1` serves PoriPati Track-1 and may serve
      later registered founder-owned projects such as w3exam; no project gets a
      duplicate stack by default, and admission remains subject to the IaC
      plan's access, data, isolation and measured-capacity gates
- [ ] Postiz vs Mixpost final call. The founder-approved multi-project
      requirement is now a selection constraint: the exact deployed edition
      must demonstrate project-scoped organization/workspace authorization
      within budget. Mixpost documents multiple workspaces under Enterprise;
      surface an exact-edition test and monthly-cost table rather than silently
      choosing Postiz or a paid Mixpost tier.
- [ ] Approval bot: custom Telegram bot vs Hermes gateway
- [ ] Per-brand X usage (worth $2–3/mo per brand?)
- [ ] Media archival: purge-only vs B2 push
- [ ] Run a second-device break-glass retrieval drill for the two Dholbeat age
      keys (public-recipient SHA-256 fingerprints `32a10a74…0f849` and
      `bed909c0…a969b`). Deferred 2026-08-17 until a device is available; this
      drill is required before the first provider-issued production secret is
      encrypted to these recipients.

## 10. Change log

| Date | Change |
| --- | --- |
| 2026-08-12 | Extracted from PoriPati AI_GROWTH_ENGINE_PLAN.md (Track 2) as a standalone project seed: brand-profile model, VPSDime hosting, Hermes batch roles, costs, phases |
| 2026-08-12 | Named **Dholbeat** (dholbeat.com + GitHub handle verified available); seeded as this repository's README/plan; scope removed from the PoriPati repo |
| 2026-08-12 | Repo configured for parallel Claude Code + Codex work: `AGENTS.md` (+ `CLAUDE.md` symlink), per-agent worktree lanes (`scripts/new-worktree.sh` / `rm-worktree.sh` / `lanes.sh`), cross-review + handoff protocol (`docs/agents/parallel-work.md`), skeleton `brands/ stack/ n8n/ prompts/` |
| 2026-08-13 | Founder approved two $7/month Linux6GB VPSDime services in the existing account: `core-1` for Paperclip/n8n/Hermes and `publish-1` for the selected publisher. The [IaC plan](docs/plans/two-vps-infrastructure-as-code.md) supersedes the earlier single-host topology and adopts SOPS+age secrets plus Paperclip configuration-parity convergence. |
| 2026-08-13 | Reserved `chayan.me` as the two-VPS operations/admin namespace, preserved Paperclip at `team.chayan.me`, and required Cloudflare Tunnel plus default-deny Cloudflare Zero Trust Access for every human-facing interface; `dholbeat.com` remains the product/marketing domain decision. |
| 2026-08-14 | Founder approved `core-1` n8n as the central trusted workflow runtime for Dholbeat and registered founder-owned external workloads, initially PoriPati Track-1. Dholbeat owns runtime/security/recovery; each consumer repository owns its workflows and product rules. No separate PoriPati n8n stack is planned. |
| 2026-08-14 | Generalized the two-host plan so shared tools are multi-project-ready from first deployment: manifest-scoped n8n consumers, one same-image Hermes container with a verified data/state boundary per project, and separate publisher organizations/workspaces. This is trusted logical/process separation with measured shared capacity, not universal tenant isolation; product applications, databases and Paperclip remain isolated. |
| 2026-08-16 | Founder approved native auto-merge for `develop` and `main`, accepting that an exact-head opposite-model approval plus green required checks may merge without a separate final human merge click; the founder must still initiate every review round. |
| 2026-08-17 | Issue #9: updated brand template and contract checks for prompt/publish policy safety, workflow source/index/schema validation, and prompt/brand documentation drift correction (`brands/README.md` §4, `_template.yaml`, `README.md`); added bounded-cost and workflow normalization checks in fixtures/tests. |
| 2026-08-17 | Issue #10: defined production inventory, secret ownership/SOPS, and immutable release-identity contracts with fail-closed validation. |
| 2026-08-17 | Founder accepted a byte-identical NordPass download-and-restore round trip for both Dholbeat age keys as satisfying the initial recovery gate; the second-device break-glass drill is deferred until a device is available and remains required before encrypting the first provider-issued production secret. |
| 2026-08-17 | Standardized top-level Claude Code and Codex response EOF markers with shell-measured GMT+6 timestamps, elapsed duration, deterministic status precedence, and an explicit non-interactive-output boundary. |
| 2026-08-22 | Issue #11: founder approved one disposable VPSDime Linux6GB ($7, single month) as the WP-05A acceptance target for the shared-host baseline. Cancel it manually once the evidence is accepted; no automation deletes provider resources. Platform marginal cost remains unchanged at $0. |
| 2026-08-23 | Issue #13: added the production host baseline contract for `publish-1` plus the `scripts/infra-plan`, `scripts/infra-apply`, and `scripts/infra-verify` command contract. Production mutation now requires an annotated release, a byte-identical pre-apply plan digest, and interactive founder confirmation; CI can never apply. Adds the already-approved `$7/month` `publish-1` line, taking two-VPS infrastructure to about `$14-15/month` including expected R2. |
| 2026-08-23 | Founder directed that `publish-1` administration must not be bound to a specific source IP and should use WireGuard as w3exam and PoriPati do, with `publish-1` running its own WireGuard server so the two hosts stay independently operable; `core-1` may join later as a separate decision. Split into its own issue: issue #13 bootstraps with an interim IP-bound SSH allowlist and the follow-up converts `publish-1` to VPN-only administration. |

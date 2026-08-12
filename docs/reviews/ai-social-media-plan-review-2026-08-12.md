# AI-assisted social media plan review

**Reviewed:** 2026-08-12  
**Plan reviewed:** the founding plan in `README.md`  
**Perspective:** a solo founder operating one brand first, then two, with a target of 1–2 hours per brand per week and roughly $10–25/month of marginal platform spend  
**Price basis:** public USD list prices, before tax, card fees, and currency conversion. Prices and platform rules should be rechecked when buying or submitting an app for review.

## Executive verdict

The overall design is sound: keep brand knowledge in profiles, use AI for evidence synthesis and first drafts, require a human decision before publishing, and keep the workflows reproducible from git. The proposed stack can become a useful solo-founder system.

It should **not be deployed exactly as written**, however. Four assumptions need to change first:

1. **Postiz does not fit the documented VPS headroom.** The plan expects only 8–10 GB free after cleanup. Postiz documents a 20 GB supported disk floor and a 50 GB recommendation; its canonical stack includes Postiz, PostgreSQL, Redis, and Temporal. The existing 6 GB RAM is below the 8 GB recommendation as well. The README's approximate 1 GB Postiz estimate is therefore not a safe capacity basis. [Postiz system requirements](https://docs.postiz.com/installation/system-requirements)
2. **Competitor and trend research cannot be fully automated through official social APIs.** TikTok explicitly excludes creators, advertisers, and commercial users from its Research Tools, and Meta's research access is intended for qualified academic/nonprofit research. A commercial founder needs a hybrid process: automate public web/YouTube/owned analytics and manually supply selected competitor links or screenshots. [TikTok Research Tools eligibility](https://developers.tiktok.com/products/research-api/), [TikTok Research API FAQ](https://developers.tiktok.com/doc/research-api-faq), [Meta Content Library overview](https://about.fb.com/news/2023/11/new-tools-to-support-independent-research/)
3. **The $0 video line is incorrect if ElevenLabs is used commercially.** ElevenLabs' free plan has no commercial license; Starter is currently $6/month and includes one. CapCut is usable as an editor, but its ordinary Sounds are non-commercial and its Commercial Sounds are licensed only for CapCut, TikTok, and TikTok for Business unless separate rights are obtained. [ElevenLabs pricing](https://elevenlabs.io/pricing), [ElevenLabs commercial-use guidance](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform), [CapCut Materials License Agreement](https://www.capcut.com/clause/material-license-agreement?lang=en)
4. **A flat-rate Codex subscription should not be the production cost baseline.** `codex exec` can run scheduled jobs, but OpenAI recommends API keys as the default for automation; ChatGPT-managed authentication is an advanced option. Subscription use has shared five-hour windows and may also have weekly limits. Hermes/Codex can be an opportunistic worker, but the pipeline should still work through a metered API with a hard budget. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex usage and pricing](https://learn.chatgpt.com/docs/pricing)

My recommended direction is:

- Pilot **PoriPati only for six weeks**.
- Keep n8n, Claude API, Telegram approval, Nano Banana 2, a scripted Bangla text renderer, CapCut as an editor, and Cloudflare R2.
- Use native/manual scheduling during the pilot.
- Defer Postiz until the host passes a capacity gate and the selected release passes duplicate-post, provider, and security tests.
- Defer X, Threads, and Bluesky until a primary channel proves traction.
- Start with two core ideas per brand per week, then adapt each idea to channel-native outputs. Do not promise 3 reels plus 1–2 statics per brand until measured founder time supports it.

Under those conditions, a two-brand steady-state cash budget of roughly **$7–17/month** is realistic without paid voice or X. With ElevenLabs and X enabled for both brands, a safer allowance is **$15–33/month**, before any VPS upgrade.

## Tool-choice review

| Tool or choice | Decision | Cost view | Detailed feedback |
| --- | --- | --- | --- |
| **n8n Community Edition** | **Keep** | $0 license fee; not $0 operationally | A good visual orchestrator for schedules, API calls, approvals, retries, and metrics. Export every workflow JSON to git. Community Edition's external binary-data storage is not the same as Postiz media storage: n8n's S3 execution-data feature is Enterprise-only, so Community Edition still needs aggressive local execution pruning. [n8n execution-data guidance](https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/manage-execution-data), [n8n external binary storage](https://docs.n8n.io/hosting/scaling/external-storage/) |
| **Claude API** | **Keep, with model routing** | Budget $4–8/month for two brands | Use Haiku 4.5 for extraction, classification, caption variants, and simple rewrites. Use Sonnet 5 for weekly synthesis and final risk/quality review only. Batch processing gets a 50% token discount. Current standard prices are $1/$5 per million input/output tokens for Haiku 4.5 and $2/$10 for Sonnet 5; web search is $10 per 1,000 searches plus tokens. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| **Hermes using flat-rate Codex auth** | **Optional experiment; remove from critical path** | Marginal cash may be $0, but capacity is shared and limited | Do not route publishing, approval state, or time-sensitive weekly jobs through it. If retained, use it for noncritical offline synthesis with a Claude API fallback. The third-party Hermes integration and its authentication behavior still need a controlled test. Never copy `auth.json` into a container or repository; OpenAI describes it as password-equivalent. [Codex automation authentication](https://learn.chatgpt.com/docs/non-interactive-mode) |
| **Telegram Bot API + custom n8n flow** | **Keep; prefer over Hermes gateway** | $0 | This is the smallest deterministic approval surface. Use buttons for Approve, Edit, and Reject; expire old approvals; and store the decision outside Telegram. Telegram is the interface, not the source of truth. |
| **Postiz self-hosted** | **Good feature fit, conditional infrastructure fit** | $0 software fee; meaningful hosting, setup, patching, and app-review effort | It covers the desired providers and has an API, but the current host fails the documented disk gate. Self-hosting also means configuring each provider app. TikTok needs a public HTTPS/verified media domain, and unaudited clients can publish only privately. New unverified YouTube API projects also have private-only uploads until audit. [Postiz TikTok setup](https://docs.postiz.com/providers/tiktok), [TikTok Direct Post restrictions](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post), [YouTube upload audit rule](https://developers.google.com/youtube/v3/docs/videos/insert) |
| **Postiz production readiness** | **Require a release gate** | Mostly founder time | As of this review, an open, user-reported Postiz issue describes a Temporal retry path that can duplicate a successful social post repeatedly. Treat it as a release-blocking test case: either wait for a verified fix or prove the chosen release cannot reproduce it and provide a kill switch. Postiz supports only its latest release for security, and its 2026 advisory history makes staging and prompt patching essential. [Open duplicate-post issue](https://github.com/gitroomhq/postiz-app/issues/1321), [Postiz security policy/advisories](https://github.com/gitroomhq/postiz-app/security) |
| **Mixpost** | **Do not switch blindly** | Lite $0; Pro $299 one-time with one year of updates | Lite only publishes to Facebook Pages, X, and Mastodon, so it does not meet the IG/TikTok/YouTube requirement. Pro supports the full set and approval flow, but $299 consumes almost the whole first-year platform budget when amortized at $24.92/month, before AI or hosting. It still needs MySQL, Redis, workers, FFmpeg, provider apps, and operational care. Trial it only if Postiz fails the capacity/reliability bake-off. [Mixpost pricing and platform comparison](https://mixpost.app/pricing), [Mixpost server requirements](https://docs.mixpost.app/server/), [Mixpost worker tiers](https://docs.mixpost.app/guides/horizon/) |
| **Hosted Postiz** | **Fallback, not budget fit** | $29/month for 5 channels; $39 for 10; $49 for 30 | The desired two-brand map has more than 10 non-Telegram accounts, so the $49 tier is the first obvious fit. That exceeds the entire stated marginal budget but may still be cheaper than founder time plus a VPS upgrade. Use the trial only if self-host operations become a distraction. [Postiz pricing](https://postiz.com/pricing) |
| **Nano Banana 2** | **Keep as the one default image API** | About $0.067 per 1K output today | Gemini 3.1 Flash Image is paid-only and currently prices 1K output at about $0.067. Generate at 1K, allow no more than three candidates, and upscale only a selected winner. Do not pay for both Nano Banana and Flux on every asset. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| **Flux through fal.ai** | **Fallback only** | Variable, generally low per image/megapixel | Keep it as a fallback for backgrounds or a failed Nano Banana prompt class. Record model, price, dimensions, attempts, and accepted result so the fallback earns its complexity. [fal pricing](https://fal.ai/pricing) |
| **Canva Free** | **Keep for exceptions; replace in the routine path** | $0 | Manual Canva work erodes the promised time saving and is hard to reproduce. Build recurring layouts as HTML/CSS templates rendered to PNG, with Noto Sans Bengali or another tested font. Let the image model create only backgrounds/objects; overlay every Bangla word programmatically. Canva remains useful for one-off campaigns. |
| **CapCut** | **Keep as editor only** | $0 editor; asset licenses vary | Use founder-owned footage, separately licensed stock, and cross-platform-cleared audio. Do not assume CapCut's included music is safe for simultaneous Facebook, Instagram, YouTube, and TikTok commercial posts. |
| **ElevenLabs** | **Optional paid tool** | $6/month Starter | First test founder-recorded voice: it is cheaper and more authentic for PoriPati. If AI voice measurably reduces time or improves completion rate, use the paid commercial tier and store the license/source metadata. Do not use free-plan output commercially. |
| **AI video generation** | **Defer** | Unbounded retries make per-clip list price misleading | Remove Hailuo/Kling from the base budget. A usable clip often needs multiple generations, editing, captions, and review. Add a provider later only for a proven content format, behind a per-campaign cap. Recheck pricing and commercial terms at that time. |
| **Cloudflare R2 Standard** | **Add** | Likely $0 at pilot scale; budget $0–1 | Postiz supports R2, and its free tier currently includes 10 GB-month, 1 million Class A operations, 10 million Class B operations, and free egress. Use a public custom media domain for provider pulls and lifecycle rules so media cannot grow without bound. [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [Postiz uploads/storage](https://docs.postiz.com/configuration/uploads) |
| **X API** | **Defer or hard-cap** | Exact endpoint prices are visible in the developer console, not the public pricing page | The fixed $2–3/brand estimate is not auditable from X's public documentation. X now uses prepaid, per-operation billing with no monthly minimum and supports spending limits/alerts. If enabled, start with a $1–5 monthly cap per brand and measure qualified traffic; do not use paid X reads for broad trend research. [X usage and billing](https://docs.x.com/x-api/fundamentals/post-cap) |

Provider onboarding is a project cost even when API calls are free. A self-hosted scheduler supplies the connector code, not universal provider credentials. For example, Postiz requires a founder-owned Meta app; its instructions warn that development-mode Facebook posts may be visible only to app roles, while public applications can require business verification and advanced permissions. Estimate and track setup/review hours per provider, and do not promise an automation launch date before the real brand accounts pass public-visibility tests. [Postiz Facebook provider setup](https://docs.postiz.com/providers/facebook), [Postiz Instagram provider setup](https://docs.postiz.com/providers/instagram)

## The research plan needs an evidence-first redesign

The phrase “weekly niche trend scan, competitor pages” suggests access that the official APIs do not reliably provide to a commercial founder. TikTok Research Tools specifically say commercial users are ineligible. Logged-in scraping or unofficial APIs would introduce account risk, brittle selectors, secret handling, and ongoing maintenance—the opposite of a low-touch solo-founder system.

Use three evidence lanes instead.

### 1. Automate sources that are legitimately accessible

- The brand's own native post and account insights, fetched at fixed windows rather than continuously.
- YouTube public search for niche queries, recent videos, channels, and visible metadata. Its search endpoint currently has a separate 100-call/day bucket, which is ample for a small weekly sweep if queries are narrow. [YouTube Search API](https://developers.google.com/youtube/v3/docs/search/list)
- Search/web results, RSS feeds, trade publications, product reviews, public forums where access is permitted, and relevant government/industry sources.
- Website analytics, Search Console queries, landing-page conversions, marketplace searches, support questions, sales objections, and customer interviews. These are often better business signals than “viral” competitor posts.
- Each brand's own comment and message themes, after removing unnecessary personal data before sending text to an LLM.

### 2. Make competitor observation a small founder input

Once a week, the founder spends 10–15 minutes per active brand in native apps and sends 5–10 links or screenshots to the brand's Telegram inbox. The bot asks for one optional note: “Why did this catch your attention?” This keeps platform access human and makes the expensive judgment explicit.

Store each observation as structured evidence:

```yaml
evidence_id: poripati-2026w33-004
source_url: https://...
observed_at: 2026-08-12T10:00:00+06:00
platform: tiktok
account: competitor-name
topic: bridal-prep
format: talking-head-list
visible_metrics: {views: 12000, comments: 83}
founder_note: "Comments contain repeated price questions"
```

Visible metrics are snapshots, not comparable ground truth. The AI should cite `evidence_id` values in every recommendation, state what is inferred, and never invent reach, audience demographics, or trend velocity.

### 3. Research at the right frequency

Use a light weekly pulse and a deeper monthly review:

- **Weekly:** own D+1/D+7 results, fresh customer questions, founder-supplied links, and 3–5 targeted web/YouTube queries.
- **Monthly:** content-pillar performance, channel focus, format changes, competitor patterns, and the next experiment.

This will be cheaper and more useful than asking an agent to perform a broad web sweep every week. “Trend” content should be a minority; evergreen problems, objections, proof, and product education should carry the calendar.

## Recommended solo-founder workflow

The publishing gate must be structural, not a sentence in a prompt. Use this state machine:

```text
evidence_collected
  -> idea_drafted
  -> idea_approved
  -> asset_ready
  -> final_approved
  -> scheduled
  -> published | failed
```

Recommended rules:

1. n8n builds a weekly evidence pack and asks Haiku for structured observations.
2. Sonnet selects a small calendar, explaining the source, audience problem, hypothesis, format, CTA, and disclosure need for each idea.
3. Telegram sends one compact idea batch. Approve/Edit/Reject callbacks are idempotent.
4. Approved ideas produce a caption, script, channel adaptations, and at most three image candidates.
5. A deterministic renderer adds Bangla/Latin text, logo, safe margins, and brand tokens. The model never renders final Bangla text.
6. Telegram sends the **exact final asset, exact per-channel caption, destinations, time, link/UTM, and AI-disclosure flag**.
7. Final approval writes a database record containing a hash of those fields. Any edit invalidates the approval.
8. Only a valid, unexpired approval hash can enter the publisher node. A failure must close safely and alert the founder; it must never silently retry an externally successful post.
9. Pull metrics once at D+1 and D+7, then append them to the experiment record.

Retain the plan's prohibition on AI-avatar testimonials. Make disclosure a required structured field, not an LLM judgment at publish time: TikTok's posting schema exposes `is_aigc`, and YouTube uploads expose `status.containsSyntheticMedia`. Founder voice and real product/process footage should be the trust-preserving default. [TikTok Direct Post schema](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post), [YouTube video upload schema](https://developers.google.com/youtube/v3/docs/videos/insert)

Use a small PostgreSQL table or another backed-up persistent store for approval and publish state. Do not rely on Telegram history or an n8n waiting execution as the only record.

### Content identity and measurement

Every core idea should receive a stable `content_id`. Store:

- brand, pillar, audience problem, hook, format, CTA, and source evidence IDs;
- generated model/version, prompt version, attempts, and variable cost;
- every destination, platform post ID, approval timestamp, publish result, and disclosure flag;
- D+1 and D+7 reach/views, watch or retention signals, saves/shares, profile actions, clicks, and qualified product actions;
- founder minutes spent on research, editing, approval, exception handling, and publishing.

Use UTMs such as `utm_source`, `utm_medium`, `utm_campaign`, and `utm_content=<content_id>` for every eligible link. Compare content **within the same platform and format**; metric definitions differ across networks and can change. Native analytics should remain the verification source for at least the first month.

The most important metric is not total engagement. Choose one business outcome per brand—for example, qualified booking/lead activity for PoriPati and a qualified learner action for w3exam—then monitor supporting signals. Also track system health: duplicate-post count, publish failure rate, approval turnaround, cost per approved asset, and founder minutes per core idea.

Do not let the researcher declare winners after a handful of posts. Accumulate at least roughly 20–30 comparable posts per brand before treating small percentage differences as a repeatable pattern; until then, report observations and confidence rather than conclusions.

## Cadence and channel focus

The current target is 3 reels plus 1–2 static posts per brand each week. Across two brands that is 8–10 original assets, before channel adaptations, two approval rounds, comments, metrics, and failures. I infer this is unlikely to stay inside 2–4 total founder hours per week during launch.

Start with:

- **One brand for six weeks.** Do not onboard w3exam until the workflow has operated for four consecutive weeks without an approval bypass, duplicate post, or unresolved publish failure.
- **Two core ideas per week.** One can become a vertical video; the other a static/carousel. Adapt them to primary channels instead of creating five unrelated originals.
- **No more than four primary destinations in the pilot.** For PoriPati, Facebook, Instagram, TikTok, and YouTube Shorts match the plan's market thesis. Publish manually/native until provider automation passes its gates. Telegram can remain a community distribution path outside the scheduler.
- **Defer X, Threads, and Bluesky.** Add a channel only when there is an audience hypothesis, a channel-native adaptation, and a success metric. Cheap cross-posting still creates review, failure, analytics, and reputation cost.
- **Three content pillars and one experiment at a time.** Example structure: problem education, proof/process, and product action. Test one hook or format variable per cycle so the metrics teach something.

A realistic weekly founder loop for one mature brand is:

| Activity | Target time |
| --- | ---: |
| Supply competitor/customer evidence | 10–15 min |
| Approve/edit two ideas | 10–15 min |
| Review two final asset packages | 20–30 min |
| Review exceptions and D+7 learning | 10–15 min |
| **Routine target** | **50–75 min** |

Reserve another 30–60 minutes per week during the first two months for provider setup, failed jobs, template refinement, and credential refreshes. That setup time should not be hidden inside the mature 1–2 hour promise.

## Revised cost model

### Assumptions

The following is a planning model, not a vendor quote:

- two active brands after the pilot;
- two core ideas per brand per week (about 16/month), with short channel adaptations;
- eight weekly brand research/synthesis jobs per month;
- approximately 0.8M Haiku input tokens + 0.15M output tokens;
- approximately 0.2M Sonnet input tokens + 0.04M output tokens;
- no more than 100 Claude web searches per month;
- about 48 Nano Banana 2 images at 1K (16 accepted static/thumbnail assets × 3 candidates);
- founder voice, no X, and existing hosting only where capacity actually permits.

At current prices, that illustrative LLM workload is approximately:

- Haiku: `(0.8 × $1) + (0.15 × $5) = $1.55`
- Sonnet: `(0.2 × $2) + (0.04 × $10) = $0.80`
- 100 web searches: `$1.00`, plus the tokens returned by search
- **Illustrative subtotal: $3.35**, before retries and unexpectedly large fetched pages

The proposed $4–8 LLM cap is therefore reasonable. Batch jobs can lower token charges, but the budget should retain the cushion rather than assume every call receives the discount.

For images, `48 × $0.067 = $3.22`, plus input tokens and retries. A **$3–6 total image budget across two brands** is a more defensible starting point than $5–10 per active brand. Enforce the candidate limit in code. If 100 1K outputs are generated, image output alone is about $6.70.

### Monthly cash scenarios

| Item | Lean two-brand target | With optional upgrades | Notes |
| --- | ---: | ---: | --- |
| n8n + approval bot software | $0 | $0 | Existing infrastructure still has capacity and maintenance cost. |
| LLM + bounded web search | $4–8 | $4–8 | Hard provider budget and usage alert. |
| Image generation | $3–6 | $3–6 | One default model; 3-candidate maximum. |
| R2 media storage | $0–1 | $0–1 | Expected to remain inside free tier initially; still set alerts/lifecycle. |
| Voice | $0 | $6 | Founder voice vs ElevenLabs Starter. |
| X | $0 | $1–5 per enabled brand | Exact price must be checked in the developer console. |
| Monitoring/backup allowance | $0–2 | $0–2 | Use existing systems if available; do not omit restore testing. |
| **Total** | **$7–17** | **$15–33 for two X-enabled brands** | Excludes VPS expansion/new host, tax, committed subscriptions, and founder time. |

The README's **$10–25/month** goal is plausible only if:

- founder voice is used or voice is not needed;
- X is deferred or tightly limited;
- the existing host genuinely passes the deployment gates;
- image candidates and web searches are capped;
- paid AI video is excluded;
- current subscriptions are treated as already committed costs.

It is not a complete all-in cost if a VPS upgrade, hosted publisher, ElevenLabs, or meaningful X research is added.

### Cost controls to implement, not merely document

- Separate project/API keys per environment and provider when supported.
- Set monthly provider budgets/alerts and a Dholbeat-side monthly counter.
- Stop generation at 80% of budget and ask the founder before spending the remainder.
- Cap fetched-page bytes, model input, output tokens, iterations, image candidates, and video attempts.
- Log estimated and actual cost against `content_id`.
- Use async batch calls for weekly work; do not use a premium model for routing or formatting.
- Do not count an existing VPS or Codex subscription as “free”; label it **committed cost / $0 marginal cash**.

## Hosting, storage, and reliability gates

### Postiz gate

Do not install Postiz on the VPS merely because `docker system prune` creates 8–10 GB. Proceed only after all of these are true:

1. At least 20 GB of durable disk is available to the Postiz stack after reserving space for the operating system, existing workloads, logs, backups, image pulls, database growth, and upgrades. Given the shared 30 GB disk, the safer answer is likely a disk expansion or separate host.
2. A seven-day staging run records RAM, swap, CPU, database, Temporal, image-pull, and disk high-water marks under scheduled workloads.
3. R2 is configured for public provider pulls through a verified media domain, with bounded lifecycle rules.
4. The selected release is the latest security-supported version, pinned by image digest in deployment; updates are staged promptly when advisories/releases appear.
5. The open duplicate-post failure class is fixed upstream or cannot be reproduced in the selected release. A kill switch can stop all publisher workers without stopping approval/research.
6. Backups of configuration and databases have been restored in a disposable environment.
7. One private/canary account per provider has completed immediate publish, scheduled publish, media, token refresh, retry, network timeout, and delete/cancel tests.

Cloudflare Access should protect the administration UI. Expose only the exact OAuth/webhook/media endpoints providers require. Disable public registration, use long unique secrets, and never place provider tokens in git or Telegram.

### n8n gate

The README correctly requires workflow exports in git. Add these operating defaults for the Community Edition:

```text
save successful production executions: none
save failed executions: all
save manual executions: false after development
pruning: enabled
maximum age: 7 days
maximum saved count: 500–1,000
production workflow concurrency: 1 during pilot
per-workflow timeout: bounded
```

n8n currently defaults to retaining successful executions and a 14-day pruning age, which is too generous for a 30 GB shared host carrying media workflows. Binary execution data remains local in Community Edition even if final assets are copied to R2, so inspect and alert on both the database and binary-data directory. [n8n execution environment variables](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/executions)

Use built-in nodes or direct HTTP requests where practical. Each community node is another dependency that can access credentials and needs separate review/pinning.

### Bounded media lifecycle

A practical starting policy is:

- rejected/generated candidates: delete within 7 days;
- working media: delete within 14 days;
- approved/published media: retain 90 days;
- reusable brand originals and templates: explicitly mark for retention;
- database backups: retain on a documented rotation and test restores.

Keep source templates, prompts, profile data, and workflow exports in git; do not put large generated binaries in git. A lifecycle should never delete media that a still-scheduled provider may need to pull.

## Six-week rollout recommendation

### Week 0: baseline and decisions

- Measure current free disk, per-container memory, database sizes, Docker storage, backup size, and current monthly committed spend.
- Pick PoriPati, two core weekly ideas, three content pillars, one primary business metric, and four primary channels.
- Record the founder's current manual time and outcomes for a comparison baseline.

### Weeks 1–2: research and approval, no auto-publish

- Build brand profile schema, evidence inbox, Claude model routing, prompt versions, cost counters, and Telegram idea/final approval.
- Render Bangla text programmatically.
- Export n8n JSON and commit it.
- Publish manually/native so content quality and founder time are evaluated independently of provider integration work.

### Weeks 3–4: metrics and templates

- Add content IDs, UTMs, D+1/D+7 metrics, and native-dashboard reconciliation.
- Keep only templates that reduce founder time without lowering quality.
- Produce a weekly report of business result, content learning, cost, founder minutes, and system failures—not a generic AI summary.

### Weeks 5–6: publisher bake-off

- If the VPS passes capacity gates, stage the latest Postiz release with R2 and canary accounts.
- Test Mixpost only if Postiz fails a documented gate; Lite is not a functional substitute for the requested channels.
- Keep native/manual publishing until every primary provider passes review/audit and failure testing.

### Exit criteria before adding w3exam

- zero unapproved or duplicate posts;
- four consecutive stable weekly runs;
- at least 90% successful scheduled publishes on tested providers, with every failure alerted and recoverable;
- median routine founder time at or below 90 minutes/week for the active brand;
- average variable AI cost at or below $2 per brand/week;
- at least one meaningful business-signal hypothesis supported or rejected;
- restore test passed and disk remains below the alert threshold during update/retry conditions.

## Specific changes I would make to the founding plan

1. Change “Postiz + postgres/redis ~1 GB” to **unverified until measured; official stack includes Temporal; host currently fails the disk floor**.
2. Change “Hermes as the ~$0 batch alternative” to **optional noncritical worker; API remains the supported fallback and budget baseline**.
3. Change “competitor pages” to **founder-supplied competitor evidence plus officially accessible sources**.
4. Change image cost from `$5–10 per active brand` to an initial **$3–6 total for two brands**, with explicit output assumptions and a hard cap.
5. Split video into **$0 founder voice** or **$6 commercial AI voice**. Remove unstable AI-video list prices from the base budget.
6. Replace fixed X `$2–3/brand` with **console-verified pricing and a $1–5/brand experimental spend cap**; default off.
7. Make **native/manual scheduling** an explicit Phase 0 and move Postiz behind capacity, security, duplicate-post, provider-review, and restore gates.
8. Start at **two core ideas/week for one brand**, measure time for six weeks, then raise cadence or add the second brand.
9. Add a formal approval hash/state machine, edit invalidation, idempotency, publish kill switch, and D+1/D+7 metric windows.
10. Add a cost ledger that distinguishes license fee, marginal usage, committed subscription/hosting, setup labor, and contingency.

## Final recommendation

Build the smallest system that improves the founder's decisions before building the full publisher. In order: evidence inbox, AI synthesis, brand-aware drafts, deterministic assets, Telegram approval, measurement, and only then automated cross-posting.

The best near-term tool set is **n8n + Claude API + Telegram + scripted HTML/CSS image templates + Nano Banana 2 + R2 + native schedulers**. Postiz remains the preferred full-feature candidate, but only after a capacity upgrade or new placement and a successful production-readiness bake-off. Mixpost Lite is not feature-complete; Mixpost Pro and hosted Postiz are reasonable time-saving alternatives but do not fit the first-year marginal budget cleanly.

This ordering protects the scarce resource in the plan: not tokens or image credits, but the solo founder's attention.

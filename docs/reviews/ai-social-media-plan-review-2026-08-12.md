# AI-assisted social media plan review

**Reviewed:** 2026-08-12  
**Plan reviewed:** the founding plan in `README.md`  
**Perspective:** a solo founder operating PoriPati and w3exam from the first week, with a target of 1–2 hours per brand per week and roughly $10–25/month of marginal platform spend

**Price basis:** public USD list prices, before tax, card fees, and currency conversion. Prices and platform rules should be rechecked when buying or submitting an app for review. Server observations are from a read-only SSH inspection on 2026-08-12; no service, file, package, plan, or account was changed.

## Executive verdict

The overall design is sound: keep brand knowledge in profiles, use AI for evidence synthesis and first drafts, require a human decision before publishing, and keep the workflows reproducible from git. The proposed stack can become a useful solo-founder system.

It should **not be deployed exactly as written**, however. Four assumptions need to change first:

1. **The $14 VPSDime tier remains the cost-optimized self-hosting choice, but the live reason is different from the README's estimate.** The current host has 6 GiB RAM and a nominal 30 GB root disk. At inspection it used only about 1.1 GB RAM and had about 5.0 GiB available, but disk was 82% full. Paperclip accounted for roughly 614 MiB RAM; all three w3exam containers together accounted for only about 190 MiB RAM and approximately 1.36 GB of removable disk. Moving w3exam therefore will not release the assumed 8–10 GB. The real disk consumer is Paperclip's broken, duplicative backup path. Repair that first, preserve Paperclip itself, then upgrade to $14 for 12 GB RAM/60 GB SSD before adding the complete Paperclip + Hermes + n8n + Postiz stack. The $21 tier is unnecessary until measured peaks prove otherwise. [Postiz system requirements](https://docs.postiz.com/installation/system-requirements), [VPSDime Linux plans](https://vpsdime.com/linux-vps)
2. **Competitor and trend research cannot be fully automated through official social APIs.** TikTok explicitly excludes creators, advertisers, and commercial users from its Research Tools, and Meta's research access is intended for qualified academic/nonprofit research. A commercial founder needs a hybrid process: automate public web/YouTube/owned analytics and manually supply selected competitor links or screenshots. [TikTok Research Tools eligibility](https://developers.tiktok.com/products/research-api/), [TikTok Research API FAQ](https://developers.tiktok.com/doc/research-api-faq), [Meta Content Library overview](https://about.fb.com/news/2023/11/new-tools-to-support-independent-research/)
3. **The $0 video line is incorrect if ElevenLabs is used commercially.** ElevenLabs' free plan has no commercial license; Starter is currently $6/month and includes one. CapCut is usable as an editor, but its ordinary Sounds are non-commercial and its Commercial Sounds are licensed only for CapCut, TikTok, and TikTok for Business unless separate rights are obtained. [ElevenLabs pricing](https://elevenlabs.io/pricing), [ElevenLabs commercial-use guidance](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform), [CapCut Materials License Agreement](https://www.capcut.com/clause/material-license-agreement?lang=en)
4. **A flat-rate Codex subscription should not be the production cost baseline.** `codex exec` can run scheduled jobs, but OpenAI recommends API keys as the default for automation; ChatGPT-managed authentication is an advanced option. Subscription use has shared five-hour windows and may also have weekly limits. Hermes/Codex can be an opportunistic worker, but the pipeline should still work through a metered API with a hard budget. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex usage and pricing](https://learn.chatgpt.com/docs/pricing)

My recommended direction is:

- Run **PoriPati and w3exam from day one**, with two separate brand profiles, evidence queues, approval states, and metric views.
- Keep Paperclip on this server. Install n8n and Hermes there as planned residents, but isolate their data, credentials, networks, and resource peaks from Paperclip. n8n owns the deterministic workflow; no deadline, approval, or publish path depends on Hermes.
- Prefer the **$14 VPSDime upgrade + self-hosted Postiz + R2** as the lowest recurring-cost automated publisher, after repairing and restore-testing the Paperclip backup. The resize can happen before or after w3exam moves; w3exam timing is not a capacity blocker. Upload-Post, Metricool, hosted Postiz, and the native hybrid remain fully specified alternatives.
- Keep Claude API, Telegram approval, Nano Banana 2, a scripted Bangla text renderer, and CapCut as an editor. Hermes may absorb noncritical batch work, but a metered API fallback keeps schedules predictable.
- If attention is tight, stagger **channels**, not brands: either launch four core channels for each brand (eight scheduler connections) or the complete seven-channel footprint for each brand (fourteen connections). Telegram remains direct through the bot.
- Start with two core ideas **for each brand** per week, then adapt each idea to channel-native outputs. Do not promise 3 reels plus 1–2 statics per brand until measured founder time supports it.

The generation, storage, and monitoring baseline remains roughly **$7–17/month** for both brands without paid voice or X; n8n and Hermes add no software-license line. With the VPSDime upgrade, self-hosted Postiz makes the cash paid for the complete base system **$21–31/month**, including the whole $14 server bill. Because $7 of that server is already committed, the additional cash from today's state is **$14–24/month**. Exact comparisons appear below.

## What Postiz facilitates

Postiz is principally the **publishing operations layer**. It is useful after research and content creation have produced an approved package; it is not the complete AI social-media system.

| Area | What Postiz contributes | Boundary to keep elsewhere |
| --- | --- | --- |
| **Account and brand organization** | Connects social accounts, groups channels for repeated use, and provides customer-group/workspace-style organization for multiple brands. | Brand facts, tone, prohibited claims, and evidence still belong in the repository's brand profiles. |
| **Editorial operations** | Drafts, a day/week/month calendar, immediate or scheduled posts, reusable posting sets and signatures, repeated evergreen posts, and RSS-driven posting. | It does not decide the business objective, content pillars, or whether a competitor observation is reliable. |
| **Cross-channel publishing** | Publishes to major networks, hosts/selects media, supports per-platform copy, and can schedule comments or threads where providers allow it. | Every network still imposes format, permission, audit, and rate-limit rules. Self-hosting does not bypass those rules. |
| **Automation boundary** | REST API, webhooks, custom integrations, CLI/SDK and MCP/n8n-oriented integration options allow n8n to create and update posts. Postiz exposes a draft-to-schedule status change, which fits a Telegram approval gate. | Telegram approval should remain the authoritative human decision. n8n should create a draft, then change it to `schedule` only after the exact asset/caption hash is approved. |
| **Measurement** | Post- and channel-level analytics such as impressions and engagement, subject to each provider's available metrics. | Native analytics remain the reconciliation source; Postiz is not a full attribution or competitor-research product. |
| **Optional AI assistance** | Hosted plans advertise caption/image/video assistance and a conversational agent. | This duplicates parts of the proposed Claude/Gemini pipeline and should not be the reason to select Postiz. Research quality, Bangla typography, licensing, and approval governance remain external. |

Relevant Postiz documentation: [features and hosted pricing](https://postiz.com/pricing), [public API introduction](https://docs.postiz.com/public-api/introduction), [create a post](https://docs.postiz.com/public-api/posts/create), and [change a draft to scheduled status](https://docs.postiz.com/public-api/posts/change-status).

## Two-brand publisher options

The account count changes by channel strategy, not by whether both brands operate:

- **Core footprint:** Facebook, Instagram, TikTok, and YouTube for each brand = **8 connected social accounts**.
- **Full footprint:** those four plus X, Threads, and Bluesky for each brand = **14 connected social accounts**.
- **Telegram:** publish directly with the existing bot rather than buying another scheduler connection.

| Option | Two-brand fit and automation | Publisher/infra change from today's $7 VPS | Additional cash from today, including $7–17 baseline | Best use and main trade-off |
| --- | --- | ---: | ---: | --- |
| **Native-scheduler hybrid** | Both brands run through n8n/Telegram; approved publish packets are scheduled in Meta Business Suite, TikTok Studio, YouTube Studio, and other native tools. | **$0** | **$7–17/month** | Lowest cash and no provider-app hosting. It adds manual publishing time and fragmented analytics, but it is a complete option rather than a blocked state. |
| **Upload-Post Basic** | Two brands consume two of five profiles; each profile can connect one account on every supported platform. Full REST API, scheduling, analytics, and official n8n/Make integrations fit the existing workflow. | **$16/month equivalent, $192 billed annually** | **$23–33/month** | Best budget/API match. The free plan can connect both brands but allows only 10 uploads/month, so use it to validate both brands and exact formats before the annual commitment. X posts containing links cost another $19/month add-on; normal platform limits still apply. [Upload-Post pricing](https://www.upload-post.com/), [API/platform list](https://docs.upload-post.com/api/overview/) |
| **Metricool Starter 5** | Two brands consume two of five brand slots, with one profile per network in each brand. Unlimited publishing, reporting, long analytics history, and analysis of up to 100 competitor profiles are included. Starter has no public API, Make, Zapier, or built-in approval workflow, so Telegram remains approval and the founder transfers/schedules the approved package in Metricool. | **$20/month annual or $25 monthly** | **$27–37 annual-equivalent or $32–42 monthly** | Best dashboard/research option and the strongest consolidation candidate. X is a $10/month add-on per connected X account; API and native approval require Advanced ($53 annual-equivalent/$67 monthly). [Metricool pricing](https://metricool.com/pricing/), [plan/API limits](https://help.metricool.com/plans-add-ons-and-api-access-explained-xux1u) |
| **Postiz self-hosted on upgraded VPSDime** | Both brands use one installation, with n8n calling the Postiz API after Telegram approval. Upgrade the existing Linux VPS from 4 vCPU/6 GB/30 GB to 4 vCPU/12 GB/60 GB. | **+$7/month** ($14 total VPS) | **$14–24/month** | Best recurring-cash automated option. Complete cash including the whole VPS is $21–31. Use R2 for all media, prebuilt images, bounded logs/executions, and the canary thresholds below. Provider app review and maintenance remain founder work. [VPSDime 12 GB plan](https://vpsdime.com/buy/linux12gb) |
| **Postiz hosted** | Same Postiz workflow without server operations. Eight core accounts fit Team; fourteen full-footprint accounts fit Pro. | **$39/month Team (10 channels)** or **$49/month Pro (30)** | **$46–56** or **$56–66/month** | Fastest way to use Postiz for both brands. It remains below the repository's $75 growth ceiling in the base scenario, although it exceeds the $10–25 marginal target. [Postiz pricing](https://postiz.com/pricing) |
| **Mixpost Pro self-hosted** | Unlimited social accounts and isolated workspaces for both brands; API, webhooks, automation, analytics, and approval flow are included. | **$299 one-time** (about **$24.92/month** over year one) + hosting | **$31.92–41.92 + hosting** in year one | Good one-time-license alternative when data ownership matters. It still needs a host, MySQL, Redis, queue workers, FFmpeg, updates, and provider configuration. [Mixpost pricing](https://mixpost.app/pricing), [server requirements](https://docs.mixpost.app/server/) |

Two other credible tools were compared but are weaker at this account count:

- **Buffer Essentials** is polished and now includes API access, but per-channel billing costs $48/month for eight accounts or $76/month for fourteen on monthly billing; annual equivalents are $40 and about $63.33. [Buffer current pricing](https://support.buffer.com/article/595-features-available-on-each-buffer-plan)
- **Zernio** includes publishing, analytics, inbox, webhooks, and API on every account, but graduated per-account pricing costs $36/month for eight accounts or $60/month for fourteen, before pass-through X calls. [Zernio pricing](https://zernio.com/pricing)

### Practical selection

1. Choose **the $14 VPSDime upgrade + self-hosted Postiz** if the founder accepts maintenance in exchange for the lowest automated-publisher cash cost.
2. Choose **Upload-Post Basic** if avoiding Postiz maintenance and provider-app hosting is worth another $9/month.
3. Choose **Metricool Starter** if competitor tracking, reports, a mature dashboard, and manual final scheduling are worth more than API automation.
4. Choose **hosted Postiz** if the same feature set is worth $39–49/month to avoid server work.
5. Choose the **native hybrid** if the immediate scheduler budget is $0. Both brands still launch; only the final scheduling step stays manual.

## VPSDime sizing and cost optimization

### What the live server actually looks like

The live inspection materially improves the sizing decision. These are point-in-time measurements, not seven-day high-water marks:

| Measured item | 2026-08-12 observation | Planning meaning |
| --- | ---: | --- |
| Host allocation | about 4 vCPU, 6 GiB RAM, nominal 30 GB disk, no swap | Memory failure will be abrupt if the combined stack exceeds the cgroup limit; retain at least 2 GiB peak headroom. |
| Root filesystem | 25.65 GB used, 5.79 GB available, **82% used** | Disk is already in the alert zone; do not pull another multi-GB stack before backup repair or resize. |
| Host memory | about 1.10 GB used, 5.34 GB available | The current host is not memory-constrained. A snapshot also showed no memory or I/O pressure. |
| Paperclip | about **614 MiB RAM**, 3.48 GB image, 18.25 GB under `/srv/paperclip` | Keep the application. Its RAM is modest; its backup layout, not its live process, causes most disk pressure. |
| w3exam, all three containers | about **190 MiB RAM** | Its migration releases little RAM and need not gate the VPS resize. |
| w3exam reclaimable disk | approximately **1.36 GB** across unique images, PostgreSQL volume, writable layers, and source tree | Removing it will increase free disk to only about 7.1 GB on the current plan—not the assumed 8–10 GB improvement by itself. |
| Container health | Paperclip running since 2026-05-15 with zero restarts/OOM kills; w3exam containers healthy | Paperclip does not need to move. Preserve it through an in-place plan change and add an external health probe rather than changing the app. |

CPU samples were mostly idle even while the host load average read 4–6; on this LXC the run-queue/load signal was inconsistent with process CPU and pressure data. Do not buy extra vCPU from load average alone. Capture per-cgroup CPU, RAM, and I/O peaks for seven days after each addition.

### Paperclip backup repair is the highest-return optimization

Paperclip itself should remain unchanged, but its host-side backup wrapper needs urgent repair before any resize or new installation:

- `/srv/paperclip/backups` holds seven daily archives totaling **13.56 GB**.
- Paperclip's live data tree holds **41 hourly compressed PostgreSQL dumps totaling 3.55 GB** at the inspection point. The host job prunes that set to 24 only once per day, then puts all 24 already-compressed dumps inside another daily gzip archive.
- Each retained daily archive is therefore roughly 1.67–2.21 GB. From August 6 through August 12 its size rose about 90 MB/day; because seven versions are kept, the retained set is growing by roughly **0.6 GB/day**. A 60 or 90 GB disk would only postpone exhaustion if this continues.
- Every host backup since July 28 exits nonzero because `data/.bash_history` is unreadable. The failed run leaves the tarball behind but stops before checksum creation and final validation. The separate cleanup job retains those archives without requiring a checksum, so the current set is **unverified**, not a dependable restore set.
- The backup's 3 GB free-space precheck does not reserve space for the new 2+ GB archive. Disk alerts are already firing at 80% and above.
- The archive includes `.env` and the mounted Paperclip home, which contains credentials. Any remote copy must be client-side encrypted and private.

Repair this without altering the Paperclip application, with **restic as the only historical-retention authority**:

1. Create one fresh compressed PostgreSQL custom-format dump into a temporary filename and replace a single `latest` local dump only after `pg_dump` exits successfully. Do not feed the preceding 23 hourly dumps into the remote backup.
2. Run `restic backup` directly over that dump, `docker-compose.yml`, `.env`, and required non-database Paperclip data. Exclude the live database directory, logs, telemetry, internal backup directory, shell history, and other caches. Restic supplies client-side encryption, content integrity, deduplication, and interruption-safe repository writes; the tar/checksum layer is unnecessary. [Restic repository resilience](https://restic.readthedocs.io/en/stable/077_troubleshooting.html)
3. Apply one repository policy with `restic forget --keep-daily 7 --keep-weekly 4 --prune`, starting with `--dry-run`, then run `restic check`. Periodically use a data-reading check and restore the database/config into a disposable environment. [Restic retention policies](https://restic.readthedocs.io/en/stable/060_forget.html)
4. Put **no expiry lifecycle rule** on the private restic bucket; deleting repository objects outside restic can corrupt it. R2 lifecycle expiry remains only for the separate public media bucket.
5. After a successful disposable restore, retire the seven unverified tarballs and collapse the existing backup/cleanup cron paths into one locked job. Keep at most the single latest local dump; configure or prune Paperclip's hourly dump cache to that same non-historical bound so 24–47 copies cannot accumulate between runs.

At today's sizes, Paperclip's compressed database dumps are under 100 MB, and restic will deduplicate repeated non-database data instead of creating another roughly 2 GB archive. After w3exam removal, retirement of the seven unverified archives, and reduction of the hourly dump cache to one file, the old 30 GB host should fall from roughly 25.65 GB used to around **10–12 GB used**. This is an estimate to verify after repair, but it demonstrates why backup design dominates storage-plan choice. R2 storage for even the current 13.56 GB set would cost only a few cents beyond its 10 GB-month free allowance; budget $0–1/month for encrypted backups plus Dholbeat media rather than paying for storage that duplicate backups will eventually fill.

### The $14 tier is the sweet spot

Public VPSDime pricing checked on 2026-08-12 shows this unusually favorable step-up. The customer portal remains authoritative for any legacy-plan difference and the exact prorated amount due today. The upgrade is now mainly a **RAM and deployment-headroom purchase** for Postiz + n8n + Hermes, while backup repair solves disk growth.

| VPSDime choice | Host bill | Change from current | Resources | Assessment for this workload |
| --- | ---: | ---: | --- | --- |
| **Keep current Linux6GB** | $7/month | $0 | 4 vCPU, 6 GB RAM, 30 GB SSD, 2 TB transfer | After backup repair and w3exam removal, this can plausibly run Paperclip + bounded n8n + an isolated Hermes gateway while both brands publish through native tools or a managed publisher. It remains below Postiz's recommended RAM/disk and has no swap, so do not place the full Postiz stack here. |
| **Add 20 GB storage to current plan** | $12/month | +$5 | 4 vCPU, 6 GB RAM, 50 GB SSD | Technically reaches the disk headline but keeps RAM below recommendation. Saving $2 versus the full plan upgrade is not worth losing 6 GB RAM and 2 TB of additional transfer. |
| **Add 30 GB storage to current plan** | $14.50/month | +$7.50 | 4 vCPU, 6 GB RAM, 60 GB SSD | Dominated by the $14 plan: it costs $0.50 more and provides half the RAM. VPSDime currently charges $2.50 per extra 10 GB. [Current-plan add-ons](https://vpsdime.com/buy/linux6gb) |
| **Upgrade to Linux12GB** | **$14/month** | **+$7** | **4 vCPU, 12 GB RAM, 60 GB SSD, 4 TB transfer** | **Recommended for Paperclip + Hermes + n8n + Postiz.** It clears Postiz's 4 vCPU/8 GB/50 GB recommended headline, doubles host RAM/disk, and R2 supplies the separate upload/backup store. The single-user/two-brand load still needs a seven-day canary because Postiz's recommendation is for its own stack, not this combined host. [Linux12GB plan](https://vpsdime.com/buy/linux12gb) |
| **Keep current + add a second Linux6GB** | $14/month total | +$7 | Two isolated 4 vCPU/6 GB/30 GB boxes | Same cash and better isolation, but the Postiz box itself remains below recommended RAM/disk and introduces a second host, tunnel, backup, and network boundary. Useful as a disposable bake-off box, not the best steady state. |
| **Upgrade to Linux18GB** | $21/month | +$14 | 4 vCPU, 18 GB RAM, 90 GB SSD, 6 TB transfer | Headroom option, not the default. Choose it immediately only if Hermes must run a local browser/FFmpeg workload concurrently with Postiz, or if the founder prefers $7/month of insurance over staged measurement. Otherwise move to it only when the $14 canary crosses the explicit thresholds below; it adds no CPU. [Linux18GB plan](https://vpsdime.com/buy/vd18gb7) |

VPSDime says a Linux-plan resize is live and instant, keeps the IP, preserves data, and bills only the prorated upgrade for the rest of the current term. A downgrade is also possible if the smaller disk has room, although it produces no refund for the current term. Take and restore-test an independent backup anyway; the current Paperclip archive set does not satisfy that gate. “Live” is not a substitute for recoverability. [VPSDime upgrade/downgrade procedure](https://vpsdime.com/knowledgebase/client-area/services/upgrade-downgrade)

There is no need to block on one exact w3exam migration date. Use whichever sequence matches operational convenience:

| Sequence | What happens | When it is useful |
| --- | --- | --- |
| **Repair → resize now → install Hermes/n8n → move w3exam → stage Postiz** | Restore-test Paperclip, resize in place to $14 while current services remain, add isolated Hermes/n8n, then reclaim w3exam and deploy Postiz. | Fastest safe path. The measured w3exam footprint is small enough to coexist temporarily on 12 GB/60 GB. |
| **Repair → move w3exam → resize → install all three** | Restore-test Paperclip, complete the planned migration, remove only verified w3exam containers/images/volumes, then resize and add Hermes/n8n/Postiz. | Cleanest change window and easiest before/after disk accounting. |
| **Repair → stay at $7 with Hermes/n8n → use native or managed publishing** | Keep Paperclip plus bounded Hermes/n8n on the current plan after w3exam moves; operate both brands through native schedulers, Upload-Post, Metricool, or hosted Postiz. | Zero infrastructure increase when self-hosted Postiz is not worth the maintenance. Both brands still start; only publisher hosting changes. |

In all three sequences, PoriPati and w3exam operate as brand profiles from the beginning. Migration of the w3exam web application is a server-maintenance concern, not a reason to postpone the w3exam social brand.

Do **not** buy these at launch:

- The **$5/month nightly-backup add-on** has only three-day retention. Because the stack is reproducible from git, start with encrypted PostgreSQL/config backups to a private R2 bucket and test restores. Buy VPS snapshots later if their faster whole-server recovery is worth $60/year.
- **Additional vCPU at $5/core** is unnecessary before measurements; the base four vCPUs already match Postiz's recommendation.
- VPSDime's **$20 one-time offloaded MySQL** service does not help: Postiz requires PostgreSQL, not MySQL.
- A **Storage VPS** is useful for large archives, not the live PostgreSQL/Temporal volumes. R2 Standard is cheaper and operationally simpler at this initial scale.

### Cash comparison using the server already being paid for

The following includes the complete current/upgraded VPS bill and the $7–17 two-brand generation/storage/monitoring baseline. It excludes optional voice, X, tax, and founder labor.

| Publishing path | Server + publisher cash | Complete base-system cash | Additional cash from today's $7 VPS state |
| --- | ---: | ---: | ---: |
| **Native hybrid** | $7 | **$14–24/month** | **$7–17/month** |
| **Upgrade VPSDime + self-host Postiz** | $14 | **$21–31/month** | **$14–24/month** |
| **18 GB headroom tier + self-host Postiz** | $21 | **$28–38/month** | **$21–31/month** |
| **Keep VPS + Upload-Post Basic** | $7 + $16 annual-equivalent | **$30–40/month** | **$23–33/month** |
| **Keep VPS + Metricool Starter** | $7 + $20 annual-equivalent / $25 monthly | **$34–44 / $39–49** | **$27–37 / $32–42** |
| **Keep VPS + hosted Postiz Team** | $7 + $39 | **$53–63/month** | **$46–56/month** |
| **Keep VPS + hosted Postiz Pro** | $7 + $49 | **$63–73/month** | **$56–66/month** |

The recommended $14 self-hosted route saves **$9/month or $108/year** versus Upload-Post Basic, **$32/month** versus hosted Postiz Team, and **$42/month** versus hosted Postiz Pro. That cash comparison needs a founder-time check: at a $20/hour value for founder time, the $108 annual Upload-Post saving pays for only **5.4 hours/year** of extra Postiz setup and maintenance. Self-hosting remains economically attractive only if operations stay deliberately boring. The backup defect already demonstrates that unattended infrastructure has a real attention cost; alerts must represent verified recoverability, not merely the presence of archive files.

### Lean one-box architecture

Use the VPS for the existing Paperclip control plane, orchestration, and publishing—not local model inference or routine media computation:

```text
Paperclip (existing, unchanged)          Hermes gateway + bounded cron
             |                                      |
             +--------- isolated projects ----------+
                                                    v
Claude/Gemini APIs -> n8n -> Telegram approval -> Postiz -> providers
                         |                         |
                    durable state              R2 media

Paperclip DB/config + Dholbeat DB/config -> encrypted private R2 backups
```

- Keep Paperclip in its existing Compose project and bind mount. Do not let n8n, Postiz, or Hermes mount `/srv/paperclip`, join its host network, or access its embedded PostgreSQL port.
- Run Hermes from its official container with only its own persistent data and a narrow Dholbeat workspace mounted. Keep its shell/file work inside that container; do not mount the Docker socket, host root, Paperclip data, or global credential directories, and do not select the host/SSH terminal backend. Keep dangerous-command approval enabled, use a Telegram allowlist/pairing rule, enable unattended tool-loop hard stops, and bind its API/dashboard to loopback or omit them. Hermes' own security policy says in-process approval and scanners are not containment; the container boundary is load-bearing. A Docker terminal backend would require extra daemon access from this deployment, so the smaller safe posture is the outer official container with narrow mounts. [Hermes Docker deployment](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/docker.md), [Hermes security policy](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- Give n8n its own database/user and persistent directory. Start production concurrency at one and use it—not Hermes—as the deterministic owner of approval and publish state.
- Run the official prebuilt Postiz Docker Compose stack: Postiz, PostgreSQL, Redis, and Temporal. Do not build Postiz from source on production.
- Set Postiz `STORAGE_PROVIDER=cloudflare`; never retain the authoritative media library on the 60 GB disk. Use two buckets: a custom-domain media bucket that providers can fetch and a completely private, client-side-encrypted restic bucket with no object-expiry lifecycle. A prefix is not an adequate public/private boundary. R2's Standard free tier currently covers 10 GB-month, one million Class A operations, ten million Class B operations, and free egress. [Postiz R2 configuration](https://docs.postiz.com/configuration/r2), [R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- On the **media bucket only**, use prefixes/lifecycle rules such as `candidates/` 7 days, `working/` 14 days, and `published/` 90 days. Keep brand originals only when explicitly marked. Restic `forget`/`prune` exclusively controls retention in the backup bucket. [R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- Keep image/video generation in external APIs and editing on the founder's normal tools. Send platform-ready media to Postiz; do not add a local LLM, generative-video service, or routine transcoding workload.
- Stagger resource peaks: run n8n research/generation batches outside the publishing window, set n8n production concurrency to one initially, and do not overlap Hermes batch work with Postiz upgrades or large video publishes.
- As initial guardrails rather than capacity claims, cap the Hermes gateway/batch container near 2 GB RAM and one concurrent agent job, and cap n8n near 1.5 GB RAM with one production execution. Alert on throttling/OOM and relax or resize from measurements. Do not add a new limit to Paperclip during this project.
- Keep Hermes' browser/Playwright and FFmpeg-heavy jobs off by default. The official Docker guide calls for 1 GiB shared memory when browser tools are enabled; repeated local browser or transcoding concurrency is the clearest reason to choose the $21 headroom tier. Hermes supports cron through the gateway and no-agent jobs that consume no model tokens, so use script-only checks for disk/health alerts. [Hermes cron](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
- Put Docker JSON-log rotation on every service, prune n8n executions, and send final media directly to R2. A bigger disk is headroom, not permission for unbounded retention.
- Keep Temporal UI disabled or behind an on-demand Compose profile in steady state. It is diagnostic UI, not part of the publish path.
- Start with Postiz's own PostgreSQL/Redis topology. After one stable month, sharing a PostgreSQL cluster with n8n through separate databases/users is an optional small optimization—not a launch dependency.
- Expose administration UIs only through Cloudflare Access. Publish only the OAuth, webhook, and required media endpoints; keep PostgreSQL, Redis, Temporal, Hermes, and Paperclip's internal services private.

The live host has two `cloudflared` processes and passes tunnel credentials through the `--token` process argument. That makes the secret visible in process inspection, an especially poor fit before installing an agent capable of running commands. The installed cloudflared 2026.3.0 supports `--token-file`: rotate the existing tunnel token after the change window, store the replacement in a file readable only by the service account, and use `--token-file`/`TUNNEL_TOKEN_FILE`. Also confirm whether two daemons are intentional; Cloudflare recommends one service instance with additional routes on a host. [Cloudflare Tunnel token-file parameter](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/), [Cloudflare Tunnel troubleshooting](https://developers.cloudflare.com/cloudflare-one/troubleshooting/tunnel/)

Postiz v2.23.0, the latest release during this review, adds streamed provider uploads to reduce worker memory and a pending-post workflow intended to prevent duplicate posts. That strengthens the case for the 12 GB box. The older duplicate-loop report remains open, however, so reproduce that exact failure class before connecting automatic publishing to production accounts. [Postiz v2.23.0 release](https://github.com/gitroomhq/postiz-app/releases/tag/v2.23.0), [open duplicate-loop report](https://github.com/gitroomhq/postiz-app/issues/1321)

### Upgrade and canary gates

The point-in-time disk, memory, container, directory, and backup measurements above are now captured. Before a plan change, add the missing time-series and recovery evidence:

```text
24-hour and 7-day RAM/CPU high-water marks
current monthly transfer
one newly verified Paperclip backup and a successful disposable restore
```

Then use **Manage VPS → Upgrade/Downgrade → Linux12GB**, confirm the customer-specific recurring and prorated totals, and pay only after the independent backup is restorable. No subscription purchase or account change was performed as part of this review.

Run both brands from the first week, but use private/canary destinations for the publisher failure tests. Promote automatic publishing only when:

- after w3exam removal and backup repair, the pre-Postiz host uses roughly 10–12 GB; investigate rather than normalizing anything above 15 GB;
- steady-state disk use after Postiz is below 36 GB (60%), the warning fires at 42 GB (70%), and nonessential generation pauses at 48 GB (80%);
- at least 12 GB remains free during an update with both current and replacement images present;
- seven-day peak RAM stays below 10 GB with no OOM kill, uncontrolled swap/thrashing, or overlapping batch spike;
- Paperclip remains reachable through its existing path, the scheduled restic snapshot and repository check succeed, and no new service can reach its bind mount or embedded database;
- both brand workspaces pass immediate/scheduled publish, token refresh, timeout, cancel, and delete tests on every enabled provider;
- the duplicate-loop reproduction does not repeat a post, the publisher kill switch works, and Telegram approval cannot be bypassed;
- database/config restore succeeds on a disposable environment and R2 media URLs remain valid for provider pulls.

Move to the $21/18 GB/90 GB plan if lifecycle/pruning cannot keep disk below 42 GB, seven-day peak RAM repeatedly exceeds 10 GB, or needed Hermes browser/transcoding jobs cannot be staggered without memory failures. Because the $21 plan still has four vCPUs, a sustained CPU bottleneck should first trigger workload rescheduling; buy the separately priced vCPU only if cgroup CPU—not LXC load average—is demonstrably saturated.

## Tool-choice review

| Tool or choice | Decision | Cost view | Detailed feedback |
| --- | --- | --- | --- |
| **n8n Community Edition** | **Install on this VPS** | $0 license fee; not $0 operationally | It is the right deterministic orchestrator for schedules, API calls, approvals, retries, and metrics. Give it a separate Compose project/database/user, one production execution at a time initially, bounded binary/execution retention, and no Paperclip mounts. Export every workflow JSON to git. Community Edition's external binary-data storage is not the same as Postiz media storage: n8n's S3 execution-data feature is Enterprise-only, so Community Edition still needs aggressive local execution pruning. [n8n execution-data guidance](https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/manage-execution-data), [n8n external binary storage](https://docs.n8n.io/hosting/scaling/external-storage/) |
| **Claude API** | **Keep, with model routing** | Budget $4–8/month for two brands | Use Haiku 4.5 for extraction, classification, caption variants, and simple rewrites. Use Sonnet 5 for weekly synthesis and final risk/quality review only. Batch processing gets a 50% token discount. Haiku 4.5 is $1/$5 per million input/output tokens. Sonnet 5 is $2/$10: announced at launch as introductory through 2026-08-31, but Anthropic has since made it the standard price and cancelled the scheduled increase to $3/$15. Web search is $10 per 1,000 searches plus tokens. [Anthropic pricing incl. the Sonnet 5 introductory-pricing note](https://platform.claude.com/docs/en/about-claude/pricing#model-pricing) |
| **Hermes Agent** | **Install as a planned resident; isolate and keep off the critical path** | $0 software; model/provider usage still applies | Use the official container as a bounded cron/batch worker for research and drafting. Its gateway daemon schedules cron every 60 seconds and supports script-only jobs with zero model use; it may send research notices through a separate Telegram bot/chat, but it must not own approvals. Give it its own volume and narrow workspace, with terminal/file actions confined to that container; no Docker socket, Paperclip mount, host network, or public dashboard/API. Keep approval/publish state in n8n/PostgreSQL and retain a metered API fallback for every deadline. Do not copy Paperclip's or the founder's existing `auth.json`; perform Hermes' own provider login into its isolated encrypted/permissioned volume. The project says it can run on a $5 VPS, but does not publish a precise RAM requirement, so the 2 GB guardrail is a canary value, not a vendor claim. [Hermes Agent](https://github.com/NousResearch/hermes-agent), [Hermes Docker deployment](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/docker.md), [Hermes cron](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md), [Codex automation authentication](https://learn.chatgpt.com/docs/non-interactive-mode) |
| **Telegram Bot API + custom n8n flow** | **Keep as the approval interface** | $0 | This is the smallest deterministic approval surface. Use buttons for Approve, Edit, and Reject; expire old approvals; and store the decision outside Telegram. If Hermes also uses Telegram, give it a separate bot or at least a separate chat with no publish callback credentials. Telegram is the interface, not the source of truth. |
| **Postiz self-hosted** | **Preferred recurring-cash automation path** | $0 software; VPS rises from $7 to $14/month | The Linux12GB upgrade provides 4 vCPU, 12 GB RAM, 60 GB SSD, and 4 TB transfer for a $7 marginal increase. With R2 uploads and bounded local data, both brands can share the installation. TikTok needs a public HTTPS/verified media domain, and unaudited clients can publish only privately. New unverified YouTube API projects also have private-only uploads until audit. [VPSDime Linux12GB](https://vpsdime.com/buy/linux12gb), [Postiz TikTok setup](https://docs.postiz.com/providers/tiktok), [TikTok Direct Post restrictions](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post), [YouTube upload audit rule](https://developers.google.com/youtube/v3/docs/videos/insert) |
| **Postiz production readiness** | **Canary before enabling automatic publish** | Mostly founder time | Postiz v2.23.0 adds streamed media and a pending-post duplicate-protection workflow. An older user-reported Temporal duplicate-loop issue remains open, so test that exact reproduction and provide a publisher kill switch instead of assuming the newer mechanism covers every failure path. Postiz supports only its latest release for security, making staged prompt patching essential. Both brands can continue via native or managed publishing during validation. [Postiz v2.23.0](https://github.com/gitroomhq/postiz-app/releases/tag/v2.23.0), [open duplicate-post issue](https://github.com/gitroomhq/postiz-app/issues/1321), [Postiz security policy/advisories](https://github.com/gitroomhq/postiz-app/security) |
| **Upload-Post** | **Best managed API-first candidate** | Free test; Basic $192/year ($16/month equivalent) | Its profile model is unusually favorable here: PoriPati and w3exam need two profiles even if each connects all supported networks. The Basic tier includes five profiles, unlimited uploads, scheduling, analytics, REST API, and n8n/Make support. It costs $9/month more than the VPS upgrade but removes most Postiz maintenance/provider-app hosting. Validate both real brands, all required post formats, token refresh, metrics, cancellation, and failure behavior on the free allowance before paying annually. [Upload-Post pricing](https://www.upload-post.com/), [Upload-Post API overview](https://docs.upload-post.com/api/overview/) |
| **Metricool Starter** | **Best managed research/dashboard candidate** | $20/month equivalent annually or $25 month-to-month for up to five brands | It can schedule both brands and adds competitor tracking, reporting, and long analytics history. Starter does not expose the API/Make/Zapier or its native approval system, so use Telegram approval and schedule the approved output through Metricool's UI. This is a deliberate UI-first option, not an automated Postiz substitute. [Metricool pricing](https://metricool.com/pricing/), [Metricool plan/API limits](https://help.metricool.com/plans-add-ons-and-api-access-explained-xux1u) |
| **Mixpost Pro** | **Credible one-time self-hosted option** | Lite $0; Pro $299 one-time with one year of updates | Lite only publishes to Facebook Pages, X, and Mastodon, so it does not meet the IG/TikTok/YouTube requirement. Pro supports the full set, unlimited accounts/workspaces, approval flow, API, MCP, and webhooks. It amortizes to $24.92/month in year one before AI or hosting and still needs MySQL, Redis, workers, FFmpeg, provider apps, and operational care. [Mixpost pricing and platform comparison](https://mixpost.app/pricing), [Mixpost server requirements](https://docs.mixpost.app/server/), [Mixpost worker tiers](https://docs.mixpost.app/guides/horizon/) |
| **Hosted Postiz** | **Ready-to-use Postiz option** | $39/month for 10 channels; $49 for 30 | Eight core accounts across both brands fit Team at $39; fourteen full-footprint accounts fit Pro at $49. It exceeds the marginal target but avoids VPS changes and provider-app hosting work, and the base combined total remains under the $75 growth ceiling. [Postiz pricing](https://postiz.com/pricing) |
| **Nano Banana 2** | **Keep as the one default image API** | About $0.067 per 1K output today | Gemini 3.1 Flash Image is paid-only and currently prices 1K output at about $0.067. Generate at 1K, allow no more than three candidates, and upscale only a selected winner. Do not pay for both Nano Banana and Flux on every asset. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| **Flux through fal.ai** | **Fallback only** | Variable, generally low per image/megapixel | Keep it as a fallback for backgrounds or a failed Nano Banana prompt class. Record model, price, dimensions, attempts, and accepted result so the fallback earns its complexity. [fal pricing](https://fal.ai/pricing) |
| **Canva Free** | **Keep for exceptions; replace in the routine path** | $0 | Manual Canva work erodes the promised time saving and is hard to reproduce. Build recurring layouts as HTML/CSS templates rendered to PNG, with Noto Sans Bengali or another tested font. Let the image model create only backgrounds/objects; overlay every Bangla word programmatically. Canva remains useful for one-off campaigns. |
| **CapCut** | **Keep as editor only** | $0 editor; asset licenses vary | Use founder-owned footage, separately licensed stock, and cross-platform-cleared audio. Do not assume CapCut's included music is safe for simultaneous Facebook, Instagram, YouTube, and TikTok commercial posts. |
| **ElevenLabs** | **Optional paid tool** | $6/month Starter | First test founder-recorded voice: it is cheaper and more authentic for PoriPati. If AI voice measurably reduces time or improves completion rate, use the paid commercial tier and store the license/source metadata. Do not use free-plan output commercially. |
| **AI video generation** | **Optional experiment outside the baseline** | Unbounded retries make per-clip list price misleading | Remove Hailuo/Kling from the base budget. If either brand has a proven format that needs generated video, run a capped campaign experiment and track accepted-output cost after retries, editing, captions, and review. Recheck pricing and commercial terms before that experiment. |
| **Cloudflare R2 Standard** | **Add** | Likely $0 at pilot scale; budget $0–1 | Postiz supports R2, and its free tier currently includes 10 GB-month, 1 million Class A operations, 10 million Class B operations, and free egress. Use a public custom media domain for provider pulls and lifecycle rules so media cannot grow without bound. [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [Postiz uploads/storage](https://docs.postiz.com/configuration/uploads) |
| **X API** | **Optional, with a hard cap** | Exact endpoint prices are visible in the developer console, not the public pricing page | The fixed $2–3/brand estimate is not auditable from X's public documentation. X now uses prepaid, per-operation billing with no monthly minimum and supports spending limits/alerts. If enabled, start with a $1–5 monthly cap per brand and measure qualified traffic; do not use paid X reads for broad trend research. [X usage and billing](https://docs.x.com/x-api/fundamentals/post-cap) |

Provider onboarding is a project cost even when API calls are free. A self-hosted scheduler supplies the connector code, not universal provider credentials. For example, Postiz requires a founder-owned Meta app; its instructions warn that development-mode Facebook posts may be visible only to app roles, while public applications can require business verification and advanced permissions. Managed publishers can reduce this work by using vendor-managed integrations, but the exact formats and visibility still need validation on both real brands before committing. [Postiz Facebook provider setup](https://docs.postiz.com/providers/facebook), [Postiz Instagram provider setup](https://docs.postiz.com/providers/instagram)

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

- **Both brands from week one.** Give PoriPati and w3exam separate profiles, evidence packs, approvals, schedules, UTMs, and outcome metrics.
- **Two core ideas per brand per week.** For each brand, one can become a vertical video and the other a static/carousel. Adapt them to destinations instead of creating five unrelated originals.
- **Choose one of two channel scopes.** The core option publishes both brands to Facebook, Instagram, TikTok, and YouTube (eight connections). The full option also publishes both to X, Threads, and Bluesky (fourteen connections). This is a founder-time and publisher-price decision, not a reason to exclude either brand.
- **Make every enabled channel intentional.** Record its audience hypothesis, adaptation rule, and success metric. If a secondary channel adds little value, leave that channel out for both brands or handle it natively; do not pause a whole brand.
- **Three content pillars and one experiment per brand at a time.** Example structure: problem education, proof/process, and product action. Test one hook or format variable per brand per cycle so the metrics teach something.

A realistic weekly founder loop across both brands is:

| Activity | Target time |
| --- | ---: |
| Supply competitor/customer evidence for both | 20–30 min |
| Approve/edit four ideas | 20–30 min |
| Review four final asset packages | 40–60 min |
| Review exceptions and D+7 learning | 20–30 min |
| **Routine target across both** | **100–150 min** |

Reserve another 30–60 minutes per week during the first two months for provider setup, failed jobs, template refinement, and credential refreshes. That setup time should not be hidden inside the mature 1–2 hour promise.

## Revised cost model

### Assumptions

The following is a planning model, not a vendor quote:

- two active brands from the first week;
- two core ideas per brand per week (about 16/month), with short channel adaptations;
- eight weekly brand research/synthesis jobs per month;
- approximately 0.8M Haiku input tokens + 0.15M output tokens;
- approximately 0.2M Sonnet input tokens + 0.04M output tokens;
- no more than 100 Claude web searches per month;
- about 48 Nano Banana 2 images at 1K (16 accepted static/thumbnail assets × 3 candidates);
- founder voice, no X, and existing hosting only where capacity actually permits.

At current standard prices, that illustrative LLM workload is approximately:

- Haiku: `(0.8 × $1) + (0.15 × $5) = $1.55`
- Sonnet: `(0.2 × $2) + (0.04 × $10) = $0.80`
- 100 web searches: `$1.00`, plus the tokens returned by search
- **Illustrative subtotal: $3.35**, before retries and unexpectedly large fetched pages

Sonnet 5's $2/$10 rate was announced as introductory through 2026-08-31, but Anthropic has made it the standard price and cancelled the scheduled September increase to $3/$15. Even at that cancelled higher rate the subtotal would only have been $3.75, so the proposed $4–8 LLM cap holds with cushion in either case. Batch jobs can lower token charges, but the budget should retain the cushion rather than assume every call receives the discount. [Sonnet 5 pricing note](https://platform.claude.com/docs/en/about-claude/pricing#model-pricing)

For images, `48 × $0.067 = $3.22`, plus input tokens and retries. A **$3–6 total image budget across two brands** is a more defensible starting point than $5–10 per active brand. Enforce the candidate limit in code. If 100 1K outputs are generated, image output alone is about $6.70.

### Base monthly cash scenario, before publisher choice

| Item | Lean two-brand target | With optional upgrades | Notes |
| --- | ---: | ---: | --- |
| n8n + approval bot software | $0 | $0 | Existing infrastructure still has capacity and maintenance cost. |
| LLM + bounded web search | $4–8 | $4–8 | Hard provider budget and usage alert. |
| Image generation | $3–6 | $3–6 | One default model; 3-candidate maximum. |
| R2 media storage | $0–1 | $0–1 | Expected to remain inside free tier initially; still set alerts/lifecycle. |
| Voice | $0 | $6 | Founder voice vs ElevenLabs Starter. |
| X | $0 | $1–5 per enabled brand | Exact price must be checked in the developer console. |
| Monitoring/backup allowance | $0–2 | $0–2 | Use existing systems if available; do not omit restore testing. |
| **Base-system total** | **$7–17** | **$15–33 for two X-enabled brands** | Excludes the chosen publisher, VPS expansion/new host, tax, committed subscriptions, and founder time. |

The README's **$10–25/month** marginal goal is achievable with the native hybrid and with the recommended self-hosted route: the VPSDime upgrade plus the base AI system adds **$14–24/month** to today's committed $7 server. Upload-Post reaches $23–33 additional, while Metricool and hosted Postiz fit only the broader $75 growth ceiling. In every case:

- founder voice is used or voice is not needed;
- X is disabled or tightly limited;
- infrastructure cost is included if the self-hosted Postiz or Mixpost path is selected;
- image candidates and web searches are capped;
- paid AI video is excluded;
- current subscriptions are treated as already committed costs.

Do not label the $7–17 base as the complete all-in cost when a publisher, VPS upgrade, ElevenLabs, or meaningful X usage is added. The earlier two-brand option table supplies the publisher-inclusive totals.

### Cost controls to implement, not merely document

- Separate project/API keys per environment and provider when supported.
- Set monthly provider budgets/alerts and a Dholbeat-side monthly counter.
- Stop generation at 80% of budget and ask the founder before spending the remainder.
- Cap fetched-page bytes, model input, output tokens, iterations, image candidates, and video attempts.
- Log estimated and actual cost against `content_id`.
- Use async batch calls for weekly work; do not use a premium model for routing or formatting.
- Do not count an existing VPS or Codex subscription as “free”; label it **committed cost / $0 marginal cash**.

## Hosting, storage, and reliability

### Postiz deployment choices and readiness

n8n is the required deterministic orchestrator on this server. Hermes is a planned isolated resident for opportunistic research/batch work, but remains off the critical path. Postiz is a publisher choice rather than a prerequisite for launching the two brands. Choose one of these routes:

1. **Recommended single box: upgrade the current VPS to Linux12GB for $14/month.** Keep Paperclip, install isolated Hermes/n8n, and stage Postiz after backup repair. Its 4 vCPU, 12 GB RAM, and 60 GB SSD match or exceed Postiz's recommended headline; R2 supplies the separate media/backup store. The marginal infrastructure cost is $7/month.
2. **Lowest infrastructure cash: stay at $7 after w3exam moves.** Repair the backup and run Paperclip + isolated Hermes/n8n, while both brands use native scheduling, Upload-Post, Metricool, or hosted Postiz. This is a working architecture, not a blocked or one-brand trial.
3. **Single-box headroom: upgrade to Linux18GB for $21/month.** Use this when concurrent Hermes browser/media work is required or the 12 GB canary exceeds 10 GB peak RAM. It costs another $7/month but adds no CPU.
4. **Isolation alternative: add another $7 Linux6GB host.** It keeps Postiz away from existing workloads for the same combined $14 bill, but the Postiz node itself remains below the recommended 8 GB/50 GB and doubles operational surfaces. It is a short bake-off option, not the preferred production topology.

The live host has only 5.79 GB disk available; w3exam removal alone raises that to only about 7.1 GB. Backup repair is what should bring the pre-Postiz host near 10–12 GB used. After repair and, for self-hosted Postiz, the resize, enable automatic publishing only after these readiness checks:

1. The 60 GB filesystem stays below the 60% steady-state and 70% warning thresholds defined in the VPSDime section, including existing workloads, logs, databases, current images, and one replacement-image set.
2. A seven-day staging run records RAM, swap, CPU, database, Temporal, image-pull, and disk high-water marks under scheduled workloads.
3. R2 is configured for public provider pulls through a verified media domain, with bounded lifecycle rules.
4. The selected release is the latest security-supported version, pinned by image digest in deployment; updates are staged promptly when advisories/releases appear.
5. The open duplicate-post failure class is fixed upstream or cannot be reproduced in the selected release. A kill switch can stop all publisher workers without stopping approval/research.
6. Paperclip and Dholbeat backups of configuration and databases have been restored in a disposable environment; no current failed/unchecksummed archive is counted as recovery.
7. One private/canary account per provider has completed immediate publish, scheduled publish, media, token refresh, retry, network timeout, and delete/cancel tests.

Cloudflare Access should protect the administration UI. Expose only the exact OAuth/webhook/media endpoints providers require. Disable public registration, use long unique secrets, move tunnel credentials out of process arguments, and never place provider tokens in git or Telegram.

### n8n operating defaults

The README correctly requires workflow exports in git. Add these operating defaults for the Community Edition:

```text
save successful production executions: none
save failed executions: all
save manual executions: false after development
pruning: enabled
maximum age: 7 days
maximum saved count: 500–1,000
production workflow concurrency: 1 during initial rollout
per-workflow timeout: bounded
```

n8n currently defaults to retaining successful executions and a 14-day pruning age, which is too generous even after moving to a 60 GB shared host carrying media workflows. Binary execution data remains local in Community Edition even if final assets are copied to R2, so inspect and alert on both the database and binary-data directory. [n8n execution environment variables](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/executions)

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

- Treat the live resource audit in this review as the point-in-time baseline: 82% disk, about 5.0 GiB available RAM, Paperclip about 614 MiB RAM, w3exam about 190 MiB RAM, and only about 1.36 GB reclaimable from w3exam.
- Replace the Paperclip tar/cleanup pair with one locked restic job, produce a checked encrypted snapshot, and complete a disposable restore before resizing or pulling new application images. Keep Paperclip itself in place.
- Rotate the Cloudflare tunnel token, use token-file mode, and confirm whether both running tunnel daemons are intentional before giving Hermes a command surface on the host.
- Create separate profiles for **PoriPati and w3exam**. Give each two core weekly ideas, three content pillars, and one primary business metric.
- Choose the eight-account core footprint or fourteen-account full footprint; both choices include both brands.
- Choose immediate-resize or migration-first sequencing; neither choice postpones a brand. Use the $14 VPSDime/self-hosted Postiz path as the default evaluation; keep the $7/native-or-managed route, Upload-Post free validation, Metricool Starter, and hosted Postiz as measured alternatives.
- Record the founder's current manual time and outcomes for both brands as the comparison baseline.

### Weeks 1–2: research and approval, no auto-publish

- If self-hosting Postiz remains the selected path, resize to $14 after the restore test. Install n8n and Hermes as separate, restricted projects whether w3exam has moved already or is about to move; stage them one at a time and record 24-hour peaks after each.
- Build both brand profiles, separate evidence inboxes, Claude model routing, prompt versions, cost counters, and Telegram idea/final approval.
- Render Bangla text programmatically.
- Export n8n JSON and commit it.
- Publish both brands through the selected trial or native tools so content quality and founder time are measured immediately; no brand waits for publisher automation.

### Weeks 3–4: metrics and templates

- Add content IDs, UTMs, D+1/D+7 metrics, and native-dashboard reconciliation.
- Keep only templates that reduce founder time without lowering quality for the relevant brand.
- Produce a separate weekly report for each brand covering business result, content learning, cost, founder minutes, and system failures—not a generic AI summary.

### Weeks 5–6: select and harden the publisher

- **Upload-Post path:** connect a profile for each brand and test every required format, scheduling, analytics, token refresh, timeout, cancellation, and duplicate protection before buying Basic annually.
- **Metricool path:** connect a Metricool brand for each business, validate competitor tracking and reports, and measure the manual time from Telegram approval to final scheduling.
- **Postiz path:** confirm the earlier Paperclip restore evidence is still valid, configure R2, and stage the latest supported Postiz release on the resized host. Connect both brand groups and use canary posts before automatic publishing. Hosted Postiz remains the no-server variant.
- **Mixpost path:** evaluate Pro only if its one-time-license and self-host model are preferable; Lite is not a substitute for the requested channels.
- **Native path:** keep both brands on native scheduling and optimize the Telegram publish packet so the manual step is fast and auditable.
- Retain a native/manual fallback for both brands until every automated provider passes visibility, permission, retry, and failure testing.

### Exit criteria before increasing cadence or channel count

- zero unapproved or duplicate posts;
- four consecutive stable weekly runs across both brands;
- at least 90% successful scheduled publishes on tested providers, with every failure alerted and recoverable;
- median routine founder time at or below 150 minutes/week across both brands;
- average variable AI cost at or below $2 per brand/week;
- at least one meaningful business-signal hypothesis supported or rejected for each brand;
- restore test passed and disk remains below the alert threshold during update/retry conditions.
- Paperclip remains stable and isolated, its scheduled restic snapshot/check succeeds, and a restore drill—not snapshot count—drives the backup health signal.

## Specific changes I would make to the founding plan

1. Change “Postiz + postgres/redis ~1 GB” to **unverified until measured; official stack includes Temporal; current $7 host lacks headroom for the combined stack; the $14 VPSDime tier is the cost-optimized candidate**.
2. Change “Hermes as the ~$0 batch alternative” to **planned isolated installation for gateway/batch work, but noncritical worker at runtime; API remains the supported fallback and budget baseline**.
3. Change “competitor pages” to **founder-supplied competitor evidence plus officially accessible sources**.
4. Change image cost from `$5–10 per active brand` to an initial **$3–6 total for two brands**, with explicit output assumptions and a hard cap.
5. Split video into **$0 founder voice** or **$6 commercial AI voice**. Remove unstable AI-video list prices from the base budget.
6. Replace fixed X `$2–3/brand` with **console-verified pricing and a $1–5/brand experimental spend cap**; default off.
7. Replace “w3exam migration + prune frees 8–10 GB” with the measured result: **w3exam releases about 1.36 GB; Paperclip's failed nested backups are the disk problem**.
8. Make **Paperclip backup repair + the $14 VPSDime upgrade + R2 + self-hosted Postiz** the recurring-cash recommendation, with the $7/native-or-managed route, Upload-Post, Metricool, and hosted Postiz retained as explicit two-brand alternatives.
9. Start **both brands at two core ideas/week each**. If workload is high, reduce destinations or cadence symmetrically instead of postponing a brand.
10. Add a formal approval hash/state machine, edit invalidation, idempotency, publish kill switch, and D+1/D+7 metric windows.
11. Add a cost ledger that distinguishes license fee, marginal usage, committed subscription/hosting, setup labor, and contingency.

## Final recommendation

Run **PoriPati and w3exam together from the first week** through the same evidence, creation, Telegram approval, and measurement architecture, while keeping their data and decisions separate.

My first choice for low-cost automation is **Paperclip unchanged on the existing VPSDime server, its host backup repaired, the server upgraded to the $14 Linux12GB tier, and isolated Hermes + n8n + Claude API + Telegram + scripted HTML/CSS image templates + Nano Banana 2 + R2 + self-hosted Postiz added alongside it**. w3exam can move before or after the resize. This gives both brands API publishing for a $7/month infrastructure increase and keeps complete base-system cash near **$21–31/month**, or **$14–24 additional** beyond today's committed $7 server.

This recommendation is conditional on a verified Paperclip restore, seven-day resource canary, and duplicate-post test. If Postiz consumes more than roughly 5.4 extra founder hours per year at a $20/hour time value, **Upload-Post Basic** becomes economically competitive despite costing $9/month more. If competitor analysis and a polished dashboard matter more than automatic handoff, use **Metricool Starter** at $20 annual-equivalent/$25 monthly. Hosted Postiz is the operationally simpler $39–49 option; the $7/native hybrid keeps Paperclip, Hermes, n8n, and both brands active with no publisher fee. Mixpost Pro remains a credible $299 one-time alternative.

This ordering protects the scarce resource in the plan: not tokens or image credits, but the solo founder's attention.

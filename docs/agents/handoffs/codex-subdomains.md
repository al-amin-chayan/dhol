# codex/codex-subdomains

Agent: codex

Head: 9c35758

## What changed

- Recorded `chayan.me` as the only public application namespace for workloads
  on `core-1` and `publish-1`.
- Preserved Paperclip's existing `team.chayan.me` hostname instead of inventing
  a migration to `paperclip.chayan.me`.
- Assigned `n8n.chayan.me` and `publish.chayan.me` as the initial human-facing
  hostnames and `hooks.chayan.me` as Telegram's machine-only n8n ingress.
- Required every human-facing interface to use its owning host's Cloudflare
  Tunnel and a default-deny Cloudflare Zero Trust Access application, with no
  direct-origin or alternate-DNS bypass.
- Defined the narrower controls and review gate for provider webhooks, OAuth
  callbacks, public media, and external probes that cannot present an Access
  credential.
- Added rollout and acceptance checks for the namespace and access boundary.
- Reconciled `chayan.me` as the operations/admin namespace with the still-open
  `dholbeat.com` product/marketing domain decision.

## Why

The founder specified that all public-facing interfaces for the two-VPS plan
must live below their `chayan.me` domain and Cloudflare Zero Trust, and noted
that Paperclip is already mapped to `team.chayan.me`.

## Verified

- `git diff --check` passes.
- Policy wording consistently preserves `team.chayan.me`.
- The human UI policy requires Tunnel + Access + closed origin ports.
- The machine-endpoint policy does not permit a whole administration hostname
  bypass and requires a committed least-privilege manifest before exposure.
- Current Cloudflare documentation confirms that Access supports independently
  revocable service tokens for automated callers, path-specific applications,
  and an outbound-only Tunnel firewall model. It also confirms that `Bypass`
  disables Access enforcement and logging, so the plan treats it as an
  explicit machine-route exception rather than Zero Trust protection.
- Current n8n documentation confirms `N8N_WEBHOOK_URL` as the supported
  reverse-proxy webhook base (`WEBHOOK_URL` is deprecated), while Telegram's
  Bot API supports a `secret_token` delivered in the
  `X-Telegram-Bot-Api-Secret-Token` header.
- No live DNS, Cloudflare, Paperclip, VPS or other external resource was read or
  changed; this lane changes repository plans only.

## Assumed / left out

- `n8n.chayan.me` and `publish.chayan.me` are initial stable names selected for
  the implementation plan. They are not live DNS changes.
- Existing `team.chayan.me` DNS/origin routing and any Access policy details
  must be captured read-only during Phase 0; this change does not assume its
  current configuration is already compliant.
- Publisher callback paths still depend on the selected publisher and provider
  integrations. The policy requires their manifests but does not guess them.

## Round-one cross-review adjudication

Reviewer: Claude Code

Reviewed head: `9c3575892390119822a3d1c5d0d8cb4843dc8348`

- `required-1` — **accept:** removed the inbound-webhook origin-port escape
  hatch; all application ingress now uses a declared tunnel route.
- `required-2` — **accept:** declared `hooks.chayan.me`, current n8n URL
  variables, Telegram secret-header verification, and positive/negative route
  tests.
- `required-3` — **accept:** populated the handoff template's `Head` field with
  the reviewed SHA.
- `required-4` — **accept:** explicitly separated the `chayan.me`
  operations/admin namespace from the open `dholbeat.com` product/marketing
  decision.
- `suggestion-1` — **accept:** replaced the README and stack policy copies with
  links to the authoritative plan section.
- `suggestion-2` — **accept:** stated that service-token routes remain
  Access-enforced and are not exception-manifest routes.
- Merge blocker outside the diff — **accept:** the stale primary-checkout draft
  is preserved in a named Git stash and removed from the checkout before this
  branch is handed back for round-two review.

## Review focus

- Confirm every round-one required finding is resolved without creating a new
  origin bypass or exposing the n8n editor on `hooks.chayan.me`.
- Confirm the Telegram ingress uses the current n8n configuration names and
  has testable missing-secret, wrong-secret, wrong-method and wrong-path cases.
- Confirm `chayan.me` and `dholbeat.com` have distinct, non-conflicting roles.

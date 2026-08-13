# codex/codex-subdomains

Agent: codex

Head: review the current branch tip and record its exact SHA in the verdict

## What changed

- Recorded `chayan.me` as the only public application namespace for workloads
  on `core-1` and `publish-1`.
- Preserved Paperclip's existing `team.chayan.me` hostname instead of inventing
  a migration to `paperclip.chayan.me`.
- Assigned `n8n.chayan.me` and `publish.chayan.me` as the initial human-facing
  hostnames.
- Required every human-facing interface to use its owning host's Cloudflare
  Tunnel and a default-deny Cloudflare Zero Trust Access application, with no
  direct-origin or alternate-DNS bypass.
- Defined the narrower controls and review gate for provider webhooks, OAuth
  callbacks, public media, and external probes that cannot present an Access
  credential.
- Added rollout and acceptance checks for the namespace and access boundary.

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
- No live DNS, Cloudflare, Paperclip, VPS or other external resource was read or
  changed; this lane changes repository plans only.

## Assumed / left out

- `n8n.chayan.me` and `publish.chayan.me` are initial stable names selected for
  the implementation plan. They are not live DNS changes.
- Existing `team.chayan.me` DNS/origin routing and any Access policy details
  must be captured read-only during Phase 0; this change does not assume its
  current configuration is already compliant.
- Exact callback paths depend on the selected publisher and provider
  integrations. The policy requires their manifests but does not guess them.
- The primary checkout had an uncommitted overlapping draft when this lane was
  authored. It was left untouched; review and merge must use this branch diff.

## Review focus

- Confirm the policy matches the founder's requirement without renaming
  Paperclip or claiming that its current route is already Access-protected.
- Challenge whether any wording creates an origin bypass or an over-broad
  Access exception.
- Confirm service-token requirements do not replace each application's own
  authorization.
- Confirm the rollout and acceptance criteria are testable before production.

# Cloudflare discovery — 2026-09-13

Read-only discovery performed through Cloudflare MCP in the issue #12 lane.
IDs are public configuration identifiers. No tokens, private keys, object
contents or application state were requested or recorded. Registrar contact
data was omitted from the returned evidence.
This is a historical observation and must be refreshed before adoption.

## Zone and registrar

| Field | Observed value |
| --- | --- |
| Cloudflare account ID | `7512591000a1e57593bc784dad59bfc0` |
| `chayan.me` zone ID | `2c295efab57307e714b212bcab2d7c42` |
| Zone status/type | active/full |
| Expected nameservers | `coby.ns.cloudflare.com`, `nia.ns.cloudflare.com` |
| Cloudflare Registrar API | domain GET succeeded (HTTP 200) |
| Registrar expiry | `2027-04-30T15:22:16.811Z` |
| Automatic renewal | enabled |
| Registrar/provider recovery login | password-manager confirmation pending |

The registrar response shows an enabled renewal setting, not proof of a
successful future payment or a tested recovery login.

Independent parent-zone probes used root referral discovery followed by
non-recursive queries directly to two `.me` servers:

```sh
dig @a.root-servers.net me. NS +norecurse +noall +authority +additional
dig @199.253.59.1 chayan.me. NS +norecurse +noall +comments +authority +answer
dig @199.253.60.1 chayan.me. NS +norecurse +noall +comments +authority +answer
```

The root returned `a0.nic.me` → `199.253.59.1` and `b0.nic.me` →
`199.253.60.1`. Both parent queries returned `NOERROR`, with `qr` and no `rd`
flag, zero answer records and two authority NS records:

```text
chayan.me. 3600 IN NS coby.ns.cloudflare.com.
chayan.me. 3600 IN NS nia.ns.cloudflare.com.
```

These are delegation referrals from parent servers; an `aa` flag is not
required for a referral. Both observed nameserver sets match the zone's set.

## Existing adoption candidates

| Object | Existing identifier/configuration |
| --- | --- |
| Paperclip tunnel | `dba0c2c4-cca2-4876-8482-aa55ec36b18f`, `paperclip-vps`, remote configuration, status **down** |
| Paperclip DNS record | `2e7b91f7550efbf09b761c79aec315f2`, proxied CNAME `team.chayan.me` → `dba0c2c4-cca2-4876-8482-aa55ec36b18f.cfargotunnel.com`, automatic TTL |
| Paperclip ingress | `team.chayan.me` → `http://localhost:3100`, followed by `http_status:404`; WARP routing disabled; configuration version 1 |
| Paperclip Access application | `8ea0cfc9-791e-4db1-9d60-e57d077511d9`, `Paperclip`, `team.chayan.me`, session duration `24h` |
| Paperclip Access allow policy | `ac83950b-6eb2-4b62-bfb1-4599683c3fd5`, `Only me`, reusable, precedence 1, exact founder email identity |
| Publisher tunnel | `55d6ce3a-7abb-452b-b819-f2feb2fa2a58`, `dholbeat-publish-1`, **local** configuration, status healthy |
| Publisher DNS record | `71cb378fe48478308fdf1ef4bbb0c5d6`, proxied CNAME `publish.chayan.me` → `55d6ce3a-7abb-452b-b819-f2feb2fa2a58.cfargotunnel.com`, automatic TTL |

The local publisher tunnel must not be converted to remotely managed
configuration as a side effect of import. Its on-host ingress was not read.
The down Paperclip tunnel is an availability observation; this lane neither
diagnosed nor changed its connector.

## Absent or outside ownership

- Exact DNS queries found no `n8n.chayan.me` or `hooks.chayan.me` records.
- The complete Access application list contained no `publish.chayan.me`,
  `n8n.chayan.me` or `hooks.chayan.me` applications. It included Paperclip,
  uptime and unrelated project applications; those unrelated applications
  are outside this lane.
- The tunnel list contained four active (not deleted) resource objects;
  the two other objects belong to external products and are outside adoption.
- The bucket list contained eleven buckets, all named for external products,
  including a product-specific state bucket. No Dholbeat state, private
  backup or public media bucket existed in the account's default jurisdiction.
  Other jurisdictions were not inventoried, and none may be assumed absent.
- No existing backend credentials, encryption roots or state contents were
  accessed. No backend recovery/locking drill or import no-change plan exists.

DNS and Access queries were checked for successful responses and pagination:
each exact DNS query had one page; the Access list had eight applications on
one page. The tunnel list returned four objects on its requested page with
`total_count: 4`. The bucket result returned eleven buckets without a further
cursor. This inventory covers the selected Cloudflare account only.

## Evidence boundary

This record is a curated, non-secret receipt of GET operations and DNS probes,
not a checked-in provider response, plan or state snapshot. It establishes
which facts need adoption verification. It does not establish code ownership,
origin firewall protection, founder/service-token probe success, private
bucket policy, backend encryption or application availability.

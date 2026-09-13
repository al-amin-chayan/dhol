# WP-06A control-plane adoption

This lane is in progress. It has not imported a resource, initialized a
production backend, or applied a provider plan. The production declarations in
`infra/services/domains.yml` and `routes.yml` remain unchanged while recovery
and bootstrap inputs are incomplete. Observed IDs below are discovery evidence,
not a resource-ownership receipt.

## Current offline commands

Use the checksum-locked controller from a clean checkout:

```sh
scripts/controller versions
scripts/controller exec pytest -q -p no:cacheprovider infra/tests/tooling/test_cloudflare_control_plane.py
scripts/check
```

The package tests are included in `scripts/check` through the existing tooling
test suite. This initial lane does not satisfy issue #12's definition of done.
The existing `infra-plan` gate remains fail-closed when `infra/tofu/` exists:
host plans made from this lane authorize nothing until the full WP-06 adapter
can bind the external-state delta. No production deployment is attempted here.

`control_plane.py no-change-plan` accepts OpenTofu plan JSON plus an
independently reviewed address-to-identity JSON map. Each address maps to
`resource_id` (the provider's state ID) and `import_id` (the provider's possibly
composite import argument). Both must be selected from the pinned provider's
documentation and live discovery. Do not build this map from the proposed plan.

The guard requires the locked OpenTofu version and its `errored: false`
marker. OpenTofu 1.12.5 omits `complete` in plan JSON; inventory coverage,
known values, no deferred changes and successful checks are required instead.
An explicit `complete: false` also fails. An actual offline built-in-provider
OpenTofu plan regression verifies this interface without a network connection.

The guard rejects create/update/delete/replacement, unknown or deferred
values, missing inventory resources, resource drift, changed outputs, failed
checks and unexpected providers. It never prints resource values. A passing
guard is an offline check; it does not authorize an apply, verify the backend,
or prove the JSON came from a reviewed binary plan.

For an ignored plan/evidence file, use its `/workspace/.artifacts/...` path:

```sh
scripts/controller exec python infra/tofu/cloudflare/control_plane.py no-change-plan \
  --plan /workspace/.artifacts/cloudflare-import.json \
  --expected /workspace/.artifacts/cloudflare-adoption-identities.json
```

`render-ingress` reads the existing version-1 domain, route and service
registries, plus a non-secret tunnel-reference registry. Its arguments are
`--routes`, `--domains`, `--services`, `--tunnels` and `--host`. The tunnel
registry has `schema_version: 1` and a `tunnels` list; each entry has an `id`
(existing tunnel UUID), `host_id` and unique `credential_ref`. It emits only a
tunnel UUID and ingress rules, ending in `http_status:404`. The renderer checks
all routes, including routes belonging to another host, before producing output.

The initial renderer supports human, Access-enforced, whole-host routes to
loopback origins only. It checks the declaration; it does not prove the live
Access policy exists. Machine routes, path-scoped routes, private-address and
container-DNS origins deliberately fail pending their complete verification
implementation. Neither cloudflared ingress nor an Access declaration proves
HTTP-method restrictions. No configuration from this lane is installed on a host.

## Discovery and unmet gates

See [the dated discovery record](discovery-2026-09-13.md). WP-01 (issue #8)
and WP-03 (issue #10) are closed and their code is in this lane's `develop`
base. Live discovery is through the founder-authorized Cloudflare MCP. The
core host is not contacted or modified.

Remaining work before completing issue #12:

1. Confirm password-manager registrar/provider recovery and the outstanding
   second-device age recovery gate before encrypting production-issued secrets.
2. Implement and review a two-stage remote-state bootstrap with immutable root
   identifiers, client-side encryption, a tested lock and bounded independent
   state recovery. There is currently no Dholbeat backend bucket to import.
3. Select and checksum-lock a stable Cloudflare provider; implement exact
   existing-resource HCL/imports, retaining the local/remote configuration
   distinction of the two existing tunnels. Do not import other products'
   buckets or unrelated Access applications into this repository.
4. Complete the generic declarations, live policy checks, method/path/auth
   probes, machine-ingress validation and public-media/private-backup rules.
5. Run a no-change import plan and record import, clean-clone recovery and
   disposable lock-contention evidence. Complete canonical adapter integration
   and obtain founder-triggered Claude Code review.

Missing Access or future route resources must be modeled separately from
existing-resource adoption. Stop on every non-no-change plan. No create,
update or delete is authorized by issue #12; later creation/bootstrap needs
an explicit founder gate and a concrete reviewed plan. Never make a local
state file the temporary production authority.

## Backend direction to verify

Private R2 with OpenTofu's S3 backend is the initial candidate. OpenTofu
supports native `use_lockfile` locking via conditional writes, and R2 documents
conditional `PutObject` support. Compatibility must be tested with the exact
locked OpenTofu version against a disposable state key before adoption.
R2 does not implement S3 bucket versioning: independent encrypted state
recovery is mandatory, not a checkbox supplied by `encrypt = true`.
Use OpenTofu's enforced client-side state/plan encryption with a separately
recoverable password-manager root. No plaintext fallback is acceptable.

Official references consulted 2026-09-13:

- [OpenTofu S3 backend and native locking](https://opentofu.org/docs/language/settings/backends/s3/)
- [OpenTofu state and plan encryption](https://opentofu.org/docs/language/state/encryption/)
- [R2 S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/)

No backend has been selected or provisioned yet. The above is a candidate,
not tested production evidence.

## Mutation, rollback and cost

The initial tooling is offline and read-only. Rollback is reverting its commit;
Cloudflare objects and host configuration are unchanged. Future import-state
rollback must preserve provider objects, retain the encrypted pre-import state
and lock identity, and never use `destroy`. Its executable procedure remains
part of the unfinished backend package.

| Component | Monthly change |
| --- | ---: |
| Initial discovery/offline tooling | $0 |
| Candidate private R2 backend | Within the existing $0–1 R2 budget; unprovisioned |
| OpenTofu/Cloudflare provider software | $0 |

No paid component or storage resource was added.

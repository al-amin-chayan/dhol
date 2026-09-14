# Desired-state registries

These registries are the cross-file authority for service, image, domain,
route, volume, and backup-adapter IDs. WP-01 intentionally leaves them empty:
no service has passed the later work-package and founder gates yet. Synthetic
examples belong only in `infra/schemas/fixtures/`.

Every future entry must validate against the versioned schemas in
`infra/schemas/` and pass the cross-file checks wired into `scripts/check`.
Secret metadata will live in the WP-03 catalog; secret values never belong in
these files.

WP-06A supersedes the historical version-1 `routes.yml` with
[`infra/tofu/cloudflare/routes.yml`](../tofu/cloudflare/routes.yml) as the sole
edge route authority. `edge.py` validates and renders it against the host inventory
and domain registry, distinguishing adopted routes from planned promotions.
The empty legacy route collection and service `route_ids: []` / loopback exposure
describe that older service-schema contract; they do not mean no Cloudflare routes
exist. Do not add edge routes to the legacy collection or maintain a second renderer.

# Desired-state registries

These registries are the cross-file authority for service, image, domain,
route, volume, and backup-adapter IDs. WP-01 intentionally leaves them empty:
no service has passed the later work-package and founder gates yet. Synthetic
examples belong only in `infra/schemas/fixtures/`.

Every future entry must validate against the versioned schemas in
`infra/schemas/` and pass the cross-file checks wired into `scripts/check`.
Secret metadata will live in the WP-03 catalog; secret values never belong in
these files.

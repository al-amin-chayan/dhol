# Postiz publisher stack

This is the only deployable publisher adapter. DG-01 records the founder's
selection of Postiz `v2.23.0`; every image here is digest-pinned and the
six-container topology retains Postiz PostgreSQL, Redis AOF, Temporal
PostgreSQL, and Elasticsearch Visibility state. No Postiz state is classified
as rebuildable without the exact behavioral drill required by DG-01.

The application is reachable only at a loopback port. PostgreSQL, Redis,
Temporal and Elasticsearch join an internal Compose network and publish no host
port. Cloudflare R2 is the media store; local upload persistence is deliberately
absent. The media bucket's lifecycle belongs to WP-06B and must be verified
before activation.

Do not run Compose by hand. `infra/roles/publisher` renders the root-owned
runtime environment and refuses activation until the host, route and backup
dependency receipts are present. `scripts/publisher-check` renders this file
with synthetic values without contacting a host or provider.

Redis uses `noeviction` within its memory allowance; silent LRU loss is
forbidden. Postiz `/tmp` is a 256 MiB tmpfs and its high-water mark is part of
the seven-day canary.

The aggregate container memory limits total 4,536 MiB. That is a hard ceiling,
not canary evidence: production still must demonstrate less than 4.5 GiB peak
RAM, less than 18 GiB steady disk and at least 8 GiB update headroom for seven
days before any real brand account is connected.

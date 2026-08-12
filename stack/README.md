# stack/

Docker compose stack for the VPSDime host: n8n + Postiz + postgres/redis, plus
env templates and host bootstrap notes. Everything here must be reproducible
from git alone.

- `.env.example` templates only — real values live on the host and in the
  password manager.
- Disk is the binding constraint (root `README.md` §5): no unbounded volumes,
  media is purge-after-publish, keep an alert at 85%.
- Runtime data (`stack/data/`) is gitignored.

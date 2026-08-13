# stack/

Docker compose stack for the VPSDime host: n8n + Postiz + postgres/redis, plus
env templates and host bootstrap notes. Everything here must be reproducible
from git alone.

- `.env.example` templates only — real values live on the host and in the
  password manager.
- Disk is the binding constraint (root `README.md` §5): no unbounded volumes,
  media is purge-after-publish, keep an alert at 85%.
- Runtime data (`stack/data/`) is gitignored.
- `team.chayan.me` remains Paperclip's hostname. Every other human-facing
  service receives its own `chayan.me` subdomain and default-deny Cloudflare
  Access application through the owning host's Cloudflare Tunnel.
- Application ports bind only to loopback or private container networks. Any
  machine-only webhook, callback, media, or health route that cannot use an
  Access credential needs an exact-path/hostname policy and application-level
  verification; it must never bypass an entire administration hostname.

# stack/

Docker Compose desired state is split by the approved two-host boundary:
Paperclip, central n8n and per-project Hermes services belong on `core-1`; only
the founder-selected publisher and its state services belong on `publish-1`.
DG-01 selected Postiz `v2.23.0`; it is the only deployable publisher stack.
Mixpost remains decision evidence only, and the two publisher stacks must never
be deployed together.

- `.env` files are forbidden in Git. Public templates may declare names only;
  runtime values are rendered from values-only `infra/secrets/**/*.sops.yml`
  ciphertext. Age private keys and provider recovery logins remain in the
  password manager.
- Compose source is reproducible from Git, while mutable runtime data is
  application-consistently backed up to encrypted off-site storage. A laptop
  or `stack/data/` is never authoritative.
- Disk is the binding constraint (root `README.md` §5): every writable path
  needs a bound and retention owner, and generated media is purge-after-publish.
- Public hostnames, Tunnel/Access controls, origin binding and machine-route
  exceptions must follow the authoritative
  [public namespace and Zero Trust policy](../docs/plans/two-vps-infrastructure-as-code.md#public-namespace-and-zero-trust-policy).

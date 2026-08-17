# Inventory contract

`production/hosts.yml` is the committed, non-secret map of stable host,
service, and public endpoint identities. It deliberately contains no IP
address: replacement or coexistence IPs are supplied only as explicit local
operator extra-vars and must name one exact host limit.

The group variable documents are validated configuration contracts. They are
not credentials and do not authorize an apply. `all.yml` fixes the timezone,
release-receipt, local-override, and release-approval rules; each role file
binds one canonical host to its public endpoint IDs.

Run the read-only validation from a clean checkout:

```sh
scripts/check
```

No command in this work package contacts a host. The future plan/apply command
must translate this manifest to its Ansible inventory input without adding an
untracked default IP or a moving DNS dependency.

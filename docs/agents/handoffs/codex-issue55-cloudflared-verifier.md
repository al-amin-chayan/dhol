# Issue #55 — trusted Cloudflare UDP client-socket verification

Agent: Codex
Branch: `codex/issue55-cloudflared-verifier`
Base: `develop` at `78572c05c3e3373127f89ae4e9a7fa62cef39937`
Scope: `infra/` listener probe/rendered inventory/tests and this runbook/handoff.

## Cause and repair

The existing Cloudflare Tunnel connector owns wildcard unconnected UDP client
sockets. The old `ss` probe treated those as undeclared public service listeners
and blocked final verification after the approved baseline reconciliation.

Only inventory-declared role-specific Cloudflare connectors enable the new
classification. It requires the active systemd daemon, root-protected unit and
executable, root process credentials, tunnel-run command shape, stable start
time/executable inode, and an exact FD/kernel unconnected-UDP-inode match in the
high kernel ephemeral range. Unknown/shared owners, DNS-server mode, fixed UDP,
TCP, spoofed names and inspection failures retain fail-closed behavior.

This trusts the installed root-owned tunnel daemon; it does not prove a remote
peer from `ss`, which exposes no peer for these QUIC sockets. Firewall checks
remain mandatory and unchanged. No runtime command line, token or credential
is logged. No package/dependency, firewall rule or persistent service is added.

## Author evidence

- Focused listener/inventory tests: 177 passed.
- Full pinned-controller `scripts/check` is required at the published head.
- Candidate-code read-only `scripts/infra-verify` passed on `publish-1`:
  ok=29, changed=0, failed=0, unreachable=0, skipped=6.
- Live negative test: a temporary wildcard ephemeral UDP socket owned by a
  Python process renamed `cloudflared` was rejected. It never received/responded
  to traffic and was closed immediately; no ingress allowance was added.
- Cloudflare Tunnel and WireGuard stayed active; six installed publisher
  services remained healthy. Temporary probe files are removed after testing.
- Read-only live evidence is author diagnostic evidence, not a new reviewed
  production release. Current receipt/tag remains `infra-prod-20260913-1` at
  the base SHA above. No production apply or receipt rewrite uses this head yet.

## Founder-triggered review and operational follow-up

Review the complete delta, especially executable/PID/FD trust, shared-socket
and failure paths, and exact-host inventory opt-in. The author must not start
its own opposite-model review. PR/handoff publishes the exact full head SHA.

After cross-review/merge and `develop` promotion, produce a fresh plan and
reviewed release before updating production identity. Re-run complete host
verification, zero-drift plan, tunnel SSH and two-source public-SSH negative
probes; only then close #55/#45. Existing installed publisher/Cloudflare runtime
is preserved, not treated as absent. #14 route/Access acceptance, #15 scheduled
backups, #17 activation/memory canaries and persistent laptop tunnel startup
remain separate follow-ups. Monthly cost change: $0.

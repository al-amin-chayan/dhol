# Codex issue #12 initial implementation handoff

Lane: `codex/wp06a-control-plane-import`.
Worktree: `.worktrees/wp06a-control-plane-import`.
Base: `develop` at `4d8e738`.

## Scope and state

Initial work only; issue #12 stays open. Claimed paths are
`infra/tofu/cloudflare/`, route-verification tests in
`infra/tests/tooling/test_cloudflare_control_plane.py`, the existing
`infra/tests/tooling/test_plan_document.py` safety regression and this handoff.
No shared route/domain declaration, host file or controller script was edited. The other
active lanes touch inventory/playbooks/controller and separate runbooks.

Read-only Cloudflare MCP discovery identifies the two existing tunnel/DNS
boundaries and Paperclip Access. A direct parent-zone delegation check passed
against two `.me` servers. Non-secret IDs, absent objects and limits are in
`infra/tofu/cloudflare/discovery-2026-09-13.md`.

The offline no-change guard checks reviewed resource/import IDs and rejects
provider mutations, drift, incomplete/unknown/deferred changes and changed
outputs. Human loopback ingress renders deterministically from existing
schemas and rejects cross-host/project routes, public origins and shared
credential references. Machine/path-scoped origins are explicitly unfinished
and rejected; declaration validation is not live policy verification.

## Verification and remaining gates

Package tests run through the pinned controller and the canonical tooling
suite: 41 package tests passed, and `scripts/check` passed with no Ansible
lint warnings and a clean secret scan. A real offline built-in-provider OpenTofu smoke test caught that the
locked version omits `complete`; the guard now checks the actual JSON interface
and rejects other tool versions. The existing plan gate remains fail-closed
when `infra/tofu/` exists. Its regression now exercises synthetic absent/present
directories rather than assuming this work package can never begin. This
narrow test-only expansion overlaps none of the discovered live lane files;
no controller/script ownership is claimed.

No production backend exists to adopt in the default R2 jurisdiction. Issue
#12 authorizes no provider resource creation/update/deletion. Backend bootstrap,
recovery credentials/age recovery, provider lock/HCL/import implementation,
no-change import receipt, locking/recovery drills and machine/live route probe
matrix remain outstanding. See the package README for the complete list.

No provider state write, apply or host change occurred. Monthly change: $0.
Do not close #12 or describe this initial commit as an implementation-complete
WP-06A package. The author does not trigger cross-review; the founder starts
Claude Code when the reviewable head is published.

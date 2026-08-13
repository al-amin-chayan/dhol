# codex/two-vps-iac-plan

Agent: codex

Head: see PR metadata; final cross-review must record the exact revised SHA

## What changed

The detailed plan in `docs/plans/two-vps-infrastructure-as-code.md` now defines:

- two founder-approved $7/month VPSDime Linux6GB services under the existing customer account;
- `core-1` for Paperclip under configuration-parity IaC plus isolated n8n/Hermes;
- `publish-1` for the selected Postiz or Mixpost stack, with Postiz still the default and the choice still open;
- one Git repository as the desired-state authority, with Ansible Core and pinned Docker Compose primary and OpenTofu limited to supported Cloudflare resources;
- values-only SOPS+age ciphertext in Git, a committed `.sops.yaml` policy, password-manager-held age private keys and `community.sops` at apply time;
- encrypted restic state recovery, CI validation, drift detection and replacement-host drills;
- measured capacity gates, exact marginal-cost math and an independently gated $7 → $14 upgrade path for `publish-1`.

`README.md` §5/§9 and its change log now record this topology as current. `AGENTS.md` owns `infra/` and amends the secret rule to allow only policy-checked SOPS+age ciphertext. The earlier review carries a clear topology-superseded notice.

No production service, VPSDime account, DNS record, Cloudflare resource or server file was changed.

## Cross-review adjudication

**Round-one reviewer:** Claude Code

**Reviewed head:** `de94393f5e3b55160d891e0789759d5cc9fc1bb3`

**Verdict:** changes requested — three required findings and three suggestions

All findings were accepted:

1. **R1 — prior-plan contradiction:** the new plan explicitly supersedes the earlier single-Linux12GB topology, explains the founder-selected isolation trade-off and updates README §5/§9/change log.
2. **R2 — founder gate:** founder approved the two-host topology and $7/month `publish-1` purchase on 2026-08-13. The plan records the approval rather than inventing another gate.
3. **R3 — secret-policy contradiction:** Ansible Vault and temporary-file materialization were replaced by SOPS+age, with values-only `*.sops.yml`, policy-required founder/break-glass recipients, `SOPS_AGE_KEY`, `community.sops`, CI metadata checks and full underlying-secret rotation after an age-key leak.
4. **S1 — publisher option:** the plan preserves Postiz-vs-Mixpost as open and specifies which host/IaC boundaries survive a Mixpost selection.
5. **S2 — ownership:** `infra/` is registered in the repository ownership table.
6. **S3 — budget:** the initial additional cash is $14–24/month; a publisher-only upgrade raises it to $21–31 and requires a new founder cost decision because it can exceed the $10–25 target.

The founder also corrected the Paperclip invariant: immutability was replaced by capture → restore-test → parity diff → planned converge → recapture/rediff/health. Container recreation is allowed; effective configuration and image digest must remain unchanged during adoption.

Because these fixes change the reviewed head, Claude Code must perform the final cross-review on the revised SHA before merge.

## Why

Two Linux6GB services cost the same initial $14/month as one Linux12GB service and provide two isolated four-vCPU scheduling envelopes. They do not pool RAM/disk and are not genuine eight-core dedicated compute. Separating the publisher protects the Paperclip boundary and gives an independent upgrade/replacement path, provided the selected publisher passes its canary.

The founder requested no routine manual service configuration and easy migration. VPSDime documents panel-based provisioning and no supported VPSDime OpenTofu/Terraform provider or public provisioning API was found, so Ansible over SSH is the smallest dependable tool for everything after initial server purchase/key attachment.

## Verified

- VPSDime: Linux6GB is 4 shared vCPU, 6 GB RAM, 30 GB SSD, 2 TB transfer at $7/month; Linux12GB is 4 shared vCPU, 12 GB RAM, 60 GB SSD, 4 TB at $14/month.
- VPSDime documents adding another service inside the existing account and describes Linux CPU as shared while RAM/disk are dedicated.
- Postiz documents a light-use supported floor of 2 vCPU/2 GB/20 GB, a recommendation of 4 vCPU/8 GB/50 GB and an official Compose stack with PostgreSQL, Redis and Temporal.
- Mixpost documents PHP, MySQL, Redis, queue workers and FFmpeg; the common host boundary survives a switch, but its capacity must be re-benchmarked.
- Official SOPS documentation covers `.sops.yaml`, age recipients, values encryption and `SOPS_AGE_KEY`; Ansible's `community.sops` collection supplies the integration.
- Live read-only server check on 2026-08-13: Ubuntu 24.04.4 LTS; Docker 29.4.0; Compose 5.1.3; 4 vCPU; 6 GiB RAM; about 1.0 GiB used and 5.0 GiB available; no swap; 17/30 GB disk used; Paperclip about 698 MiB RAM; w3exam containers about 225 MiB combined.
- `git diff --check` passed, and the current-plan contradiction sweep found no stale Paperclip-immutability, temporary-materialization or blanket no-secrets wording.

## Assumed / left out

- This PR is a plan, not the IaC implementation. It does not install Ansible, create roles/Compose files, purchase the approved second VPS, edit the existing host or migrate w3exam.
- The second host's exact datacenter, IP and hostname depend on stock and measured latency. Different location is preferred for failure separation, but availability is not assumed.
- The password-manager product and CI runner remain founder choices; SOPS+age and its required safety properties are no longer optional.
- OpenTofu remains optional until supported Cloudflare resources are deliberately imported. It does not manage VPSDime through undocumented endpoints or browser automation.
- Recovery objectives are initial targets to verify in drills, not an uptime/SLA promise.

## Final review focus

- Confirm every prior single-host/Paperclip-immutability statement is either superseded or removed.
- Verify the SOPS policy cannot be read as permission for plaintext secrets or private age keys in Git.
- Inspect the before/after Paperclip parity and restore-before-mutation gates.
- Validate initial and escalated budget arithmetic against the $10–25 marginal target.
- Confirm the Postiz-vs-Mixpost decision stays open without weakening the two-host IaC design.
- Verify every disk-growth path has one retention authority and the restic bucket has no external expiry lifecycle.

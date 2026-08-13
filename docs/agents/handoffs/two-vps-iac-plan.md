# codex/two-vps-iac-plan

Agent: codex  
Head: pending commit

## What changed

Added `docs/plans/two-vps-infrastructure-as-code.md`, a detailed decision and implementation plan for:

- two $7/month VPSDime Linux6GB services under the existing customer account;
- `core-1` for unchanged Paperclip plus isolated n8n/Hermes;
- `publish-1` for the complete host-local Postiz stack;
- one Git repository as the desired-state authority;
- Ansible Core plus pinned Docker Compose as the primary infrastructure-as-code layer;
- optional OpenTofu only for supported Cloudflare resources, not unsupported VPSDime lifecycle automation;
- password-manager-backed secret materialization, encrypted restic state recovery, CI validation, drift detection and replacement-host drills;
- measured capacity gates and an independent $7 → $14 upgrade path for `publish-1`.

No production service, VPSDime account, DNS record, Cloudflare resource or server file was changed.

## Why

Two Linux6GB services cost the same $14/month as one Linux12GB service and provide two isolated four-vCPU scheduling envelopes. They do not pool RAM/disk and are not genuine eight-core dedicated compute. Separating Postiz protects the existing Paperclip workload and gives a better per-host upgrade path, provided Postiz passes its below-recommended 6 GB/30 GB canary.

The founder requested no routine manual service configuration and easy migration. VPSDime documents panel-based provisioning and no supported VPSDime OpenTofu/Terraform provider or public provisioning API was found, so Ansible over SSH is the smallest dependable tool for everything after initial server purchase/key attachment.

## Verified

- Current public VPSDime plans: Linux6GB is 4 shared vCPU, 6 GB RAM, 30 GB SSD, 2 TB transfer at $7/month; Linux12GB is 4 shared vCPU, 12 GB RAM, 60 GB SSD, 4 TB at $14/month.
- VPSDime documents adding another service inside the existing account, and says Linux CPU is shared while RAM/disk are dedicated.
- Postiz documents a 2-vCPU/2-GB/20-GB supported floor for light all-in-one use, 4-vCPU/8-GB/50-GB recommended, and an official Compose stack containing Postiz, PostgreSQL, Redis and Temporal.
- Ansible's maintained `community.docker.docker_compose_v2` module manages Compose v2 and check/diff mode supports previewing many configuration changes.
- Cloudflare publishes supported Terraform/OpenTofu-compatible resources for tunnels and R2, while OpenTofu warns that backend/plan data can contain sensitive material.
- Live read-only server check on 2026-08-13: Ubuntu 24.04.4 LTS; Docker 29.4.0; Compose 5.1.3; 4 vCPU; 6 GiB RAM; about 1.0 GiB used and 5.0 GiB available; no swap; 17/30 GB disk used; Paperclip about 698 MiB RAM; w3exam containers about 225 MiB combined.
- `git diff --check` passed; the added files contain no detected credential/key patterns.

## Assumed / left out

- This PR is a plan, not the IaC implementation. It deliberately does not install Ansible, create roles/Compose files, purchase the second VPS, edit the existing host or migrate w3exam.
- The second host's exact datacenter, IP and hostname depend on stock and measured latency. Different location is preferred for failure separation, but availability is not assumed.
- The exact password-manager product and CI runner remain founder choices; the interfaces and safety properties are specified without forcing a paid product.
- OpenTofu is optional until Cloudflare resources are deliberately imported. It does not manage VPSDime based on undocumented endpoints or browser automation.
- Recovery objectives are initial targets to verify in drills, not an uptime/SLA promise.
- Existing Paperclip config must be adopted in guard/read-only mode before automation owns it.

## Review focus

- Challenge whether the two-host boundary is worth its second-OS management cost and whether the fallback to one $14 host remains clear.
- Verify that “8 vCPU aggregate” is never represented as one eight-core/dedicated resource pool.
- Adversarially inspect the Postiz 6 GB/30 GB canary and $7 → $14 publisher-only escalation thresholds.
- Check that Ansible is correctly primary given VPSDime's provisioning boundary, and that optional OpenTofu has a useful but non-overstated scope.
- Look for any path that makes Git, a founder laptop, an unencrypted state file, or a single host the sole recovery authority.
- Ensure Paperclip remains unchanged during adoption and no first-run playbook could recreate/move it.
- Verify every disk-growth path has a retention authority and the restic bucket has no external expiry lifecycle.
- Review secret separation, production apply controls, cross-host trust and the no-two-node-cluster decision.

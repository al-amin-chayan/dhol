# claude/wp05a-18-interface-evidence

Agent: claude

Head: fae9c7cca9975ca71316b1035d7702cfb1fdedfb

PR: #47 — closes WP05A-18, the one finding left open on merged PR #41.

## What changed

- `infra/tests/disposable/redact_network_evidence.py` (new): redacts addresses
  and MAC addresses, keeps interface names and rule shape, derives a verdict
  from the redacted text.
- `infra/tests/disposable/run.sh`: captures `ip -o link`, the default route and
  `iptables -S DHOLBEAT-DOCKER-INGRESS` through `run_logged`, then asserts on
  the verdict. `summary.yml` gains three interface fields.
- `infra/tests/tooling/test_network_evidence.py` (new): 15 tests.
- `docs/runbooks/disposable-host-baseline.md`: those fields are required for
  the real VM/VPS repeat, which must run with no hand-added
  `dholbeat-temporary-ssh` rule.
- `README.md`: one appended §10 change-log row.

## Why

The reviewer found no interface name anywhere in the attached real-host
evidence, so the converged `-i <interface> -j DROP` rule was never shown to
match a NIC the host has. `iptables -C` passes against a rule naming an absent
interface, and `validate_contract.py`'s interface assertion leaves no trace in
retained evidence.

## Verified

- `scripts/check` passes in the pinned controller: 357 tooling tests,
  ansible-lint 0 failures / 0 warnings over 173 files.
- `infra/tests/disposable/run.sh` runs green end to end and produces
  `host-network-evidence.txt` with `default_route_interfaces: eth0`,
  `docker_ingress_drop_interfaces: eth0`, `redaction_residue: 0`.
- The artifact was scanned independently for leaks: zero residual IPv4
  addresses, zero residual MAC addresses, interface names intact.
- Failure modes fail closed, checked directly against synthetic transcripts:
  a DROP naming an absent NIC, a present-but-wrong NIC, a negated `! -i` match,
  an absent chain, and a missing command.

## Assumed / left out

- **The live VM/VPS rerun is not done and cannot be done from this repo.** It
  needs a disposable host with the console-created listener restored, two
  convergences, and no hand-added `dholbeat-temporary-ssh` rule. This PR makes
  it a stated runbook requirement.
- The container fixture's only NIC is `eth0`, which is what the fixture
  contract declares, so the fixture proves the mechanism rather than a real
  non-`eth0` NIC. `eth0` matching on a container is close to tautological.
- WP05A-19 was **not** touched: PR #44 already closed it.

## Review focus

1. **Redaction.** `redact()` runs MAC, then IPv6, then IPv4. `RESIDUE` is a
   deliberately looser detector that withholds any line still matching an
   address shape. Look for an input that leaks an address or that destroys an
   interface name.
2. **The verdict is derived from the redacted text**, not the raw transcript,
   so a reviewer can re-derive it from the file. Confirm that holds.
3. **Bounds.** The new capture goes through `run_logged`, so it is inside the
   8 MiB per-file and 64 MiB aggregate caps. Confirm nothing routes around
   `bounded_tee.py`.
4. **Fail-closed.** `assert_network_evidence` greps four verdict lines. Check
   there is no input where the evidence looks complete but the DROP rule is
   wrong.
5. A `-j DROP` with no `-i` is reported as `any` and counts as covering the
   default route; `! -i X` is reported as `not:X` and never counts. Confirm
   both readings are right.

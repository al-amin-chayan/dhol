# Production host baseline contracts

One file per production host, named `<host-id>.yml`, where `<host-id>` also
appears in `../hosts.yml`. The file is the complete non-secret answer to "what
must be true of this machine before anything mutates it, and what must the
shared baseline roles make true."

An empty directory is a valid state. A host gains a contract only when its own
work package provisions it, so `core-1` — which is adopted by configuration
parity under its own package — has none here yet.

## What belongs here

| Block | Purpose |
| --- | --- |
| `provider` | vendor, plan, account boundary, datacenter, a *pointer* to the purchase receipt, and the monthly cost |
| `expected_host` | the operating-system image, distribution, version, architecture, resource floor, and public interface asserted before mutation |
| `bootstrap` | the provider-delivered login, key-only authentication, and the **name** of the local address override |
| `admin` | the named administrator, its explicit UID, and the approved SSH **public** keys |
| `break_glass` | the tested out-of-band recovery method, its owner, and how it was verified |
| `ssh` | the port and the explicit source allowlist |
| `application_bindings` | addresses a future service may bind to — loopback or private only |
| `managed_directories` | every writable path with owner, mode, classification, size limit, retention, and backup owner |

`role_writable_paths` is **derived** from `managed_directories`, so the two
cannot drift apart.

## What must never appear here

- **A host address.** `scripts/infra-plan`, `infra-apply`, and `infra-verify`
  take `--address` on the command line. The validator rejects any bare IP
  literal outside `application_bindings`, so a replacement host needs no
  repository change.
- **Any secret.** Private keys, tokens, passwords, and provider credentials live
  in SOPS+age ciphertext or the password manager. The validator rejects
  secret-shaped keys.
- **A purchase receipt, invoice, or account identifier.** Record where it lives,
  never what it says.

## How it is checked

`scripts/check` validates every file here offline, with no host contact, against
the same `infra/roles/base/files/validate_contract.py` the convergence run uses.
The check supplies the declared `expected_host` facts and a source address drawn
from the declared allowlist, so it answers exactly the reviewer's question: if
the controller connects from inside the declared allowlist, does this contract
already hold?

Positive and negative fixtures live in
`../../fixtures/host-baseline/`. Add coverage there, not by weakening a contract.

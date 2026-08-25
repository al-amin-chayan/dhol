# Release identity and `/etc/dholbeat-release`

Production applies are manual. CI validates contracts but never creates a tag,
approves a plan, connects to a host, or writes a receipt.

The release sequence is fail-closed:

1. start from a clean `main` commit approved by the opposite model family at
   that exact SHA;
2. create an annotated tag `infra-prod-YYYYMMDD-N` that resolves to that commit;
3. record the toolchain lock, image locks, schema versions, exact target roles,
   required pre-apply backup snapshot, and SHA-256 of the redacted reviewed
   plan in a release document matching `release.schema.json`;
4. apply only that plan/tag/commit after founder confirmation; and
5. atomically write the redacted host receipt matching
   `runtime-receipt.schema.json` to `/etc/dholbeat-release` as root-owned mode
   `0644`, then verify it independently.

The receipt contains no credential, private address override, decrypted value,
database state, or plan body. It records identity and digests only. The
approved and applied plan digests must be identical; a changed plan, target,
commit, tag, toolchain lock, image lock, or backup snapshot invalidates the
authorization.

`validate.py` rejects a lightweight/missing tag, a tag pointing elsewhere, a
commit not reachable from protected `main`, review evidence for another SHA, a
wrong plan digest, and runtime drift from the release. Generated release plans
and receipts stay under gitignored `.artifacts/` until the future apply command
writes the final receipt to its host.

## Rollback boundary

A Git revert is not a universal rollback. Before apply, the operator records
the required backup snapshot and the package-specific rollback path. Stateless
configuration may converge to the preceding annotated release. Database/image
migrations, route cutovers, and provider grants follow their own reviewed
rollback procedures and restore evidence. A failed receipt check stops the
apply or leaves the affected unit inactive; it never blesses an emergency edit
as desired state.

## Examples

The files under `examples/` contain synthetic hashes and fixture identities.
They demonstrate shape only and are never production receipts or approval.

## Monthly cost

| Component | Monthly change |
| --- | ---: |
| Release and receipt validation | $0 |

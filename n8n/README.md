# n8n/

Credential-free source for Dholbeat-owned workflows on the one central n8n
runtime: research, drafting, approval routing, publishing and metrics. Export
and normalize every reviewed change so recovery never depends on the live
editor. Flows resolve brand profiles by slug and never hard-code a brand.

External founder-owned consumers remain canonical in their owning repository.
Dholbeat stores only their declarative registration and immutable reviewed
source commit; it does not vendor their workflow exports. PoriPati Track-1 is
the first consumer, not a second n8n stack or a Dholbeat workflow.

Exports contain credential names/references only. Runtime values come from the
consumer's values-only `infra/secrets/**/*.sops.yml` ciphertext, are rendered
without a decrypted workspace copy and are never committed as `.env` files.

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

## Workflow export index and source contracts

`n8n/exports/index.yml` is the canonical index of committed workflow exports.
Each workflow manifest (`workflows/*.yml`) references a normalized export under
`n8n/exports/workflows/<workflow-id>.normalized.json`. Export files must:

- contain stable metadata IDs and contract fields (`workflow_id`, `project_id`,
  `brand_id`, `owner`, `input_schema_id`, `output_schema_id`, `trigger`,
  `timeout_seconds`, retention, revision/idempotency templates),
- omit UI-volatility fields and secrets,
- avoid any direct autonomous publish action,
- be plain JSON that can be replayed in offline review procedures.

Canonical edits should follow this sequence:

1. Export workflow JSON from the editor.
2. Normalize it to remove editor/runtime volatile fields (positioning, disabled state,
   node metadata) before committing.
3. Update `n8n/exports/index.yml` and keep workflow manifest metadata (`workflow_id`,
   `project_id`, `source_path`, `source_commit`) in sync.

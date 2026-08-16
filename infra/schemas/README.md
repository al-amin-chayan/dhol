# Versioned configuration contracts

This directory contains the version-1 JSON Schemas and the project-neutral
cross-file validator for Dholbeat's desired-state manifests. JSON Schema checks
the shape of each document. `validate.py` then checks properties that require
more than one file: ID uniqueness, reference resolution, ownership, route and
origin policy, writable-path declarations, backup coverage, immutable source
pins, publisher ownership, approval gating, and Hermes mount/state isolation.

Run the same entry point used by CI:

```sh
scripts/check
```

For a focused positive-bundle check inside the pinned controller:

```sh
scripts/controller exec python infra/schemas/validate.py \
  --root /workspace --bundle infra/schemas/fixtures/positive
```

## Schema inventory

| Contract | Schema | Version |
| --- | --- | ---: |
| Inventory | `inventory.schema.json` | 1 |
| Service registry | `service.schema.json` | 1 |
| Image registry | `image.schema.json` | 1 |
| Domain registry | `domain.schema.json` | 1 |
| Route registry | `route.schema.json` | 1 |
| Volume registry | `volume.schema.json` | 1 |
| Backup-adapter registry | `backup-adapter.schema.json` | 1 |
| Secret catalog | `secret-catalog.schema.json` | 1 |
| Release receipt | `release.schema.json` | 1 |
| Brand profile | `brands/brand.schema.json` | 1 |
| Prompt manifest | `prompts/prompt.schema.json` | 1 |
| Workflow manifest | `n8n/workflow.schema.json` | 1 |
| n8n consumer | `n8n/consumers/consumer.schema.json` | 1 |
| Hermes project | `stack/hermes/projects/project.schema.json` | 1 |
| Publisher mapping | `stack/publisher/mapping.schema.json` | 1 |

## Versioning and migration

`schema_version: 1` and each schema's versioned `$id` are part of the stored
contract. Adding an optional field may remain version 1. A change that would
make an already deployed manifest invalid must add a new versioned schema,
document a deterministic migration and rollback here, and keep the prior
validator available until deployment receipts prove that every consumer has
migrated. Never rewrite a deployed schema version in place.

There are no deployed manifests at WP-01, so version 1 needs no migration. The
empty registries under `infra/services/` deliberately contain no production-
looking placeholders.

## Fixture matrix

The positive bundle contains two credential-free projects and brands. Invalid
fixtures are overlays on that bundle; tests assert the named policy failure so
a YAML parse error cannot accidentally satisfy a negative test.

| Fixture | Intended failure |
| --- | --- |
| `duplicate-id` | duplicate service ID |
| `cross-project-credential` | project-alpha service uses project-beta secret |
| `public-origin` | route origin binds publicly |
| `missing-access` | human route omits its Access policy |
| `unbounded-log` | service has no bounded log policy |
| `unbounded-volume` | volume has no size quota |
| `floating-ref` | external source follows a branch |
| `shared-hermes-mount` | two Hermes projects share `/opt/data` |
| `shared-hermes-state` | two Hermes projects share local state |
| `unknown-writable-path` | service declares a path with no volume |
| `undeclared-writable-path` | referenced volume path is absent from service declarations |
| `missing-retention` | writable volume has no retention policy |
| `unapproved-publish-transition` | publish scheduling lacks exact human approval |
| `orphan-reference` | route names an unknown service |
| `wrong-owner` | a service mounts another project's volume |
| `missing-backup-adapter` | retained data names an unknown adapter |

All fixture identities are synthetic (`project-alpha`, `project-beta`,
`brand-alpha`, and `brand-beta`). Validation performs no network, provider, or
host access and adds no monthly cost.

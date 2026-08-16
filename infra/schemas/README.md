# Versioned configuration contracts

This directory contains the version-1 JSON Schemas and the project-neutral
cross-file validator for Dholbeat's desired-state manifests. JSON Schema checks
the shape of each document. `validate.py` then checks properties that require
more than one file: ID uniqueness, reference resolution, ownership, route and
origin policy, writable-path declarations, backup coverage, immutable source
pins, publisher ownership, approval gating, and Hermes mount/state isolation.

Route origins fail closed and declare one of three forms: loopback, the route's
own registered service ID, or an RFC1918/IPv6-ULA address explicitly owned by
that service's registry entry. Unknown hostnames and cross-service origins are
invalid. Secret metadata has a binding
`allowed_principal_ids` list for every service, brand, workflow, consumer,
Hermes project, or publisher mapping that may resolve the value;
`allowed_service_ids` is the binding service-only subset.

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
migrated. Never rewrite a deployed schema version in place. `validate.py`
derives the release receipt's expected version map directly from the schema
files, so a new version must update the appropriate schema path and migration
procedure rather than a second hard-coded version list.

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
| `undeclared-principal-credential` | same-project workflow is absent from the secret's principal allow-list |
| `public-origin` | loopback route origin binds publicly |
| `cross-project-origin` | route targets another project's service |
| `cross-project-private-origin` | route uses another service's declared private address |
| `duplicate-private-origin-address` | two services on one host claim the same private address |
| `unknown-origin-host` | route targets an undeclared single-label host |
| `service-public-private-address` | service labels a public address as private |
| `missing-access` | human route uses a machine exception instead of enforced Access |
| `machine-exception-shared-domain` | machine exception shares a human administration domain |
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
| `host-unknown-service` | inventory names an unknown service |
| `host-missing-service-backref` | service's host omits the service ID |
| `route-exposure-missing` | route exposure has no route |
| `non-route-with-route` | non-route exposure retains a public route |
| `route-host-mismatch` | route and service use different hosts |
| `route-owner-mismatch` | route and service use different project owners |
| `route-retention-owner-mismatch` | route retention has the wrong project owner |
| `secret-service-project-scope` | allowed service is outside the secret's project scope |
| `workflow-brand-owner-mismatch` | workflow targets another project's brand |
| `undeclared-transition-state` | workflow transition names an undeclared state |
| `consumer-cross-project-route` | consumer uses another project's route |
| `publisher-duplicate-organization` | two projects reuse one publisher organization |
| `publisher-duplicate-workspace` | two projects reuse one publisher workspace |
| `publisher-duplicate-account` | two projects claim one social account |
| `release-missing-schema-version` | release omits a schema version |
| `release-unknown-schema-version` | release names an unknown schema |
| `release-unsupported-schema-version` | release requests a version not declared by its schema |
| `release-image-digest-mismatch` | release receipt differs from the image lock |

All fixture identities are synthetic (`project-alpha`, `project-beta`,
`brand-alpha`, and `brand-beta`). Validation performs no network, provider, or
host access and adds no monthly cost.

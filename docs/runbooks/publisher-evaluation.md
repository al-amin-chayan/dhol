# Runbook — reproduce the DG-01 publisher evaluation

Reproduces the evidence behind
[`../decisions/publisher-selection.md`](../decisions/publisher-selection.md)
from a clean checkout. Nothing here touches production, a social provider, or
the founder's VPSDime account.

## What the harness does

For one candidate it converges the pinned topology on the local container
runtime, registers three generic project fixtures, runs a seventeen-check
positive and negative authorization matrix, exercises the registration lock and
an application-consistent dump/restore drill, samples memory for the whole
topology, then destroys the stack and its volumes.

Channels are database fixture rows, never provider connections. A cross-tenant
rejection is only recorded as isolation evidence when the identical request is
accepted for the tenant's own channel, so a malformed body can never be
mistaken for an authorization boundary.

## Prerequisites

- A container runtime exposing `docker` and `docker compose` v2.
- `python3` with PyYAML, `openssl`, `curl`.
- About 6 GB of free image space and roughly 2.5 GB of free memory for the
  Postiz topology. The harness pulls two publisher images plus their databases.
- No repository secret, inventory, or SOPS key is read. Every fixture
  credential is generated per run into a temporary directory outside the
  repository and deleted when the run ends.

## Run it

```sh
infra/tests/publisher-eval/run.sh --candidate postiz
infra/tests/publisher-eval/run.sh --candidate mixpost-lite
```

Each run writes one file:

```text
.artifacts/publisher-eval/<candidate>/<variant>/evidence.json
```

`.artifacts/` is gitignored. Only the redacted summary in the decision record
is committed.

Options:

| Flag | Effect |
| --- | --- |
| `--variant ID` | Choose a topology variant; Postiz defaults to `temporal-es` |
| `--artifacts PATH` | Write evidence somewhere other than `.artifacts/publisher-eval` |
| `--keep-failed` | Leave a failed stack running for inspection instead of destroying it |

A successful run always destroys its containers, network, and volumes. With
`--keep-failed`, clean up by hand afterwards:

```sh
docker compose -p <project-printed-by-the-run> down --volumes --remove-orphans
```

## Reading the evidence

`verdict` is one of:

| Verdict | Meaning |
| --- | --- |
| `disqualified` | A check encoding the founder-approved multi-project requirement failed or is unsupported |
| `viable-with-findings` | The requirement holds but some check or drill failed |
| `viable-over-budget` | Everything passed but a **measured** capacity budget was breached |
| `viable` | Every check, drill, and measured capacity budget passed |

`viable` speaks only for what the harness measured. `unmeasured_capacity`
carries the budgets it cannot judge — update headroom needs a real 30 GB host
mid-upgrade — and the verdict never gates on those. `topology_disk_mib` is this
topology's images and volumes, a lower bound on host usage rather than the
host's steady disk.

The harness never emits `selected`. Only the founder records a selection, in
the decision record.

`unsupported` on a check means the edition has no surface to test, not that it
passed. Mixpost Lite's matrix is mostly `unsupported` because the edition ships
no machine API.

## Changing the pinned candidates

`infra/tests/publisher-eval/candidates.yml` is the reproducibility record:
edition, version, licence, and digest-pinned image. Change a pin there and in
the matching Compose file under `infra/tests/publisher-eval/compose/`, never in
`run.sh`. `scripts/check` fails on an image reference without a `sha256`
digest and on a paid edition marked evaluable.

## Drills that are expected to fail today

`cancel.terminates-workflow` fails against Postiz `v2.23.0`, and that is a
measured product finding rather than a broken harness: a cancelled post's
Temporal workflow keeps running. `backup.dump-restore` fails for the same
reason, because it re-checks the workflow after cancelling the retained post.
Both are recorded in the decision record. Do not "fix" them by relaxing the
predicate — the whole point is that the row disappearing is not the job
stopping.

## When a run wedges

The Postiz evaluation restarts the backend twice — once for the restore rebuild
and once for the registration lock. On a contended machine that backend can take
many minutes to come back, and has been observed not to come back at all inside
a twenty-minute budget. The harness fails closed in that case: it reports the
timeout and destroys the stack rather than recording a pass. Re-run it on a
quieter machine; do not raise the readiness budget to make the symptom go away,
because a publisher that will not restart is the finding.

## Reproducing the Elasticsearch finding

The decision record states that Temporal's SQL visibility store makes the
Postiz backend fail to start. Reproduce it with the other variant:

```sh
infra/tests/publisher-eval/run.sh --candidate postiz --variant temporal-sql --keep-failed
```

The run fails waiting for the backend. Read the cause from the kept stack:

```sh
docker exec <postiz-container> sh -c 'tail -40 /root/.pm2/logs/backend-error.log'
```

Expect `Unable to create search attributes: cannot have more than 3 search
attribute of type Text.` Then destroy the kept stack as shown above.

## What the harness deliberately does not do

- It does not connect a social account, complete an OAuth grant, or publish.
- It does not purchase or run a licence-gated edition. A paid edition is
  recorded in `candidates.yml` with its price and its unverified vendor claims.
- It does not run for seven days. The measured figures are a short-run bound,
  not the `WP-13` canary.
- It does not upgrade or roll back a pinned version, and it does not measure
  free space on a real 30 GB host. Update rollback and update headroom are
  `WP-13` obligations; see the decision record's disposition table.
- The restore drill destroys the Postiz and Temporal database volumes and the
  Elasticsearch index, reloads the two retained dumps, and re-verifies the
  application — including that a pending scheduled post is still queued with an
  open workflow behind it. Temporal's database is retained state, not
  rebuildable: at `v2.23.0` the recovery scan only re-queues posts already past
  due, so an empty Temporal strands every future job. The drill does not rebuild
  the whole host.
- It does not run on the production architecture. See the limitations section
  of the decision record.

# Decision records

One file per founder decision gate from
[`../plans/two-vps-reproducible-implementation-plan.md`](../plans/two-vps-reproducible-implementation-plan.md)
§7. A record is the durable answer to a gate: agents assemble the evidence and
the recommendation, the founder records the choice, and dependent work packages
read the record instead of re-litigating the question.

## Naming

`docs/decisions/<gate-subject>.md`, for example `publisher-selection.md` for
`DG-01`. The gate ID appears in the record's front matter table, not in the
file name, so a record survives a plan renumbering.

## Required structure

| Section | Contents |
| --- | --- |
| Status table | Gate ID, status, evidence run, decision date, deciding human |
| Question | The exact choice, in one sentence |
| Candidates | Every option with its exact edition, version, image digest and license |
| Evidence | What was measured, on what, with the reproduction command |
| Comparison | Like-for-like results, including failures and untested areas |
| Cost | The complete monthly founder wallet per option, not the delta |
| Reversibility | Export, restore and migration-away implications |
| Recommendation | The agent recommendation and why |
| Founder decision | Left empty until the founder fills it in |
| Limitations | Everything the evidence does not cover |

## Rules

- An agent never fills in **Founder decision**. A record whose status is not
  `decided` does not unblock its dependent work package.
- Every measured number carries the command that produced it and the
  environment it was measured on. An unmeasured claim is labelled as such.
- Evidence lives under gitignored `.artifacts/`. Only redacted summaries and
  the pins needed to reproduce a run are committed.
- Changing a decision means a new dated entry in the record's status table and
  a `README.md` §10 change-log line, never a silent edit.

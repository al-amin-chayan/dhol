# Pull-request review workflow

Every Dholbeat task is cross-reviewed by the opposite model before merge. The
founder starts every review round; the author must never start, schedule, or
delegate its own cross-review. Automation validates review evidence and merge
state, but it never invokes a reviewer.

## Review states

Every open, non-draft PR has exactly one review-state label:

| Label | Meaning |
| --- | --- |
| `review:requested` | The current head needs founder-triggered cross-review. |
| `review:changes-requested` | A formal review has an open `blocker` or `required` finding. |
| `review:ready-for-ci` | The exact current head has a formal opposite-model approval; CI and merge may proceed. |

New commits invalidate the state: restore `review:requested`, remove the other
review-state labels, and hand the new full SHA to the founder. Area labels say
what changed. Add `production-risk` when the change mutates durable or external
state. `blocked` or `decision` means the PR returns to draft, its auto-merge
request is cancelled, and the founder is asked for direction.

## Review types

### Baseline review

The first formal cross-review on a PR is the one **Baseline** review. It is an
end-to-end assessment, not fail-first triage. The reviewer must inspect the
entire implementation before returning a verdict, even after finding a
blocker. At minimum it checks:

- the issue, PR description, and every stated acceptance criterion;
- the complete base-to-head diff and affected behavior, not only highlighted
  files or the author's summary;
- `README.md`, `AGENTS.md`, repository policy, cost, disk, secret, disclosure,
  and human-approval constraints that apply;
- tests and claimed verification, including direct execution or live-state
  checks where the claim depends on them;
- failure paths, boundary conditions, and whether the implementation fixes the
  whole requirement rather than its most visible example.

The reviewer then posts one consolidated finding set for the whole
implementation. Do not drip-feed findings across comments. Every finding has:

1. a stable ID and `blocker`, `required`, or `suggestion` severity;
2. a file-and-line or other exact evidence location;
3. the failed claim, governing citation, and concrete impact;
4. an explicit ask; and
5. a probable fix or repair direction.

The suggested fix is advisory. It helps the author understand the repair path;
it is not permission to apply a patch without validating the diagnosis and
checking the proposed repair against the whole system.

### Follow-up review

Every formal review after the baseline is a **Follow-up** review. It must:

1. revisit every prior finding and the author's adjudication;
2. verify accepted fixes from files, tests, and relevant live state;
3. test any `already-done` or `reject` explanation and mark it
   `accepted-explanation`, `still-open`, or `needs-founder`;
4. inspect the complete since-reviewed delta for regressions or new findings
   introduced by the fixes; and
5. return one consolidated exact-head verdict.

A follow-up may add a finding when the changed implementation introduced or
exposed it. It must not move the goalposts by turning an unchanged area that
the baseline already covered into a new blocking requirement. Safety or secret
exposure is always surfaced immediately. If the author's evidence is sound,
the reviewer withdraws the finding rather than demanding compliance. If the
evidence remains ambiguous or the agents disagree on product intent, both stop
and ask the founder.

Baseline plus one follow-up is the normal two-round limit. Contested findings
then require a founder decision. If the founder directs another fix and
review, that and every later round remain `Follow-up`; a new baseline is never
started for the same PR.

## Author adjudication before fixes

The author does not start editing merely because a reviewer proposed a change.
First, it records one disposition for every finding:

- `accept` — the diagnosis is correct, with the affected requirement stated;
- `already-done` — existing behavior satisfies it, with file/test evidence;
- `reject` — the claim is incorrect, with reproducible counter-evidence;
- `out-of-scope` — valid but outside the task, with the tracked follow-up or
  founder decision that prevents silent deferral; or
- `needs-founder` — product intent or risk authority is genuinely ambiguous.

Only accepted findings are implemented directly. The author chooses a coherent
fix that resolves the failure class, even when it differs from the reviewer's
suggestion, and explains why. It reruns proportionate verification, rechecks
the entire author diff, changes the label to `review:requested`, and gives the
new full SHA back to the founder. The author never starts the follow-up review.

## Formal GitHub review contract

The opposite agent submits a GitHub `REQUEST_CHANGES` review when any
`blocker` or `required` finding is open and an `APPROVE` review only when none
remain. It then uses its own App to replace the review-state label with
`review:changes-requested` or `review:ready-for-ci`, respectively. `COMMENT` is
not a merge verdict. Every formal review body contains:

```text
Review type: Baseline
Reviewer: Claude Code
Reviewed head: 0123456789abcdef0123456789abcdef01234567
```

Use `Review type: Follow-up` after the baseline and the actual reviewer name
(`Codex` or `Claude Code`). `Reviewed head` is the complete 40-character PR
head. The review must be submitted by that model's own GitHub App.

The read-only `Cross-review gate` checks the PR author App, opposite reviewer
App, review sequence, formal state, markers, current head, and
`review:ready-for-ci`. It runs trusted code from `develop`; it cannot invoke a
model, change a label, approve, or merge.

## Ready PR and native auto-merge

An implementation-complete PR is ready, not draft. The author applies at least
one `area:*` label plus `review:requested`, then arms native auto-merge using
its own App identity:

```bash
# routine branch -> develop
scripts/github-app-gh pr merge <number> --repo al-amin-chayan/dhol --auto --squash

# develop -> main promotion
scripts/github-app-gh pr merge <number> --repo al-amin-chayan/dhol --auto --merge
```

GitHub performs the merge only after the formal opposite-model approval,
exact-head review gate, controller checks, current-base requirement, and thread
resolution all pass. Reviewers never merge author work. If a new commit or base
update changes the head, the author restores `review:requested`; approval and
checks must be earned again for that exact head.

## Bootstrap and reproduction

The PR that introduces this protocol is reviewed under the existing branch
rules. Do not activate its new required check before it merges: the trusted
gate script does not yet exist on `develop`, which would deadlock the bootstrap.
After that PR merges, run:

```bash
scripts/configure-github-rulesets.py --apply
```

This renames `review:approved` to `review:ready-for-ci`, converges all managed
review labels, enables native auto-merge, and adds the trusted gate to both
protected-branch rulesets. The command uses only the running agent's personal
GitHub App profile.

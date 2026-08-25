# Top-level response EOF marker

This contract applies only to the final user-facing message from Claude Code or
Codex in a top-level interactive session with the founder. It does not apply to
subagent or workflow return values, schema-constrained/structured output, file
content, commit messages, pull-request bodies, or review bodies.

## Measured workflow

Never estimate a timestamp or duration.

1. At the first available shell action after receiving a top-level request,
   before substantive repository work, run `scripts/eof-marker.sh start` and
   retain the returned epoch in turn context. This recorded instant is the
   measurable task start; do not imply precision before it.
2. Immediately before composing the final response, choose the status using
   the precedence below and run:

   ```sh
   scripts/eof-marker.sh finish --start START_EPOCH --status "STATUS"
   ```

3. Paste the command's single output line as the response's absolute final
   line. Nothing, including a citation or code fence, may follow it.

If the turn began before this contract was loaded or a start epoch was not
captured, omit `--start`; the helper emits `Duration: unavailable`. If no shell
is available at finish time, use `unavailable` for both timestamp and duration
rather than inventing values:

```text
--- EOF @ unavailable | Duration: unavailable | Status: NEEDS HUMAN ACTION ---
```

The timestamp is acquired with `TZ=Asia/Dhaka` (GMT+6 with no displayed
timezone label) and the C locale. Bangladesh does not observe daylight-saving
time. A duration below one minute is rendered as `Xs`; a duration of one minute
or longer is rendered as `Xm SSs`.

## Status precedence

Use the first matching status in this order:

1. `NEEDS HUMAN ACTION` — a concrete founder decision, authorization, or action
   is required before completion, including founder-triggered cross-review.
2. `BLOCKED` — a non-human external or tooling blocker prevents progress and no
   founder action can directly resolve it.
3. `IN PROGRESS` — autonomous agent work remains and can continue without the
   founder.
4. `DONE` — the request is complete and no required work remains.

## Exact output grammar

These are fully rendered valid markers:

```text
--- EOF @ Aug 17, 2026 | 11:05 AM | Duration: 42s | Status: DONE ---
--- EOF @ Aug 17, 2026 | 11:18 AM | Duration: 4m 12s | Status: DONE ---
```

Consumers may recognise a marker with this anchored regular expression:

```regex
^--- EOF @ (?:[A-Z][a-z]{2} [0-9]{2}, [0-9]{4} \| (?:0[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)|unavailable) \| Duration: (?:[0-9]+s|[0-9]+m [0-5][0-9]s|unavailable) \| Status: (?:DONE|IN PROGRESS|BLOCKED|NEEDS HUMAN ACTION) ---$
```

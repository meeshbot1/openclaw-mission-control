# Heartbeat

When there is an active Mission Control Codex bridge/team run, poll for progress periodically on heartbeat wakes instead of only waiting for explicit user asks. Check whether the team is still making progress, whether worker state changed, and whether it completed without a user-facing update.

For active bridge/team runs:
- check status regularly on heartbeat wakes,
- compare progress against the last observed state when possible,
- inspect tmux/logs if bridge state looks stale,
- and do not let completed or stalled runs sit silently.

Notify the user when:
- a bridge/team run stalls,
- a bridge/team run completes,
- progress materially changes and the user has not been updated,
- verification fails,
- dependency/build breakage appears,
- or a main `dev-projects` handoff is needed.

If a team appears finished in tmux/logs but not cleanly finalized in bridge state, treat that as a stalled run: inspect it, report it, and clean it up with `team-shutdown`.

Otherwise stay quiet.

# Change Report: Universal Attachment Handling

Date: 2026-05-13
Branch: amish/mission-control-dashboard-cron-error-details-20260513
Commit scope: Add repository guidance for treating message attachments as first-class task input.

## High-Level Changes

- Added repo-level guidance requiring agents to inspect and incorporate accessible attachments before answering user requests.
- Clarified fallback behavior when direct media or file tooling is unavailable.

## File And Section References

- `AGENTS.md`: added the `Universal Attachment Handling` section under the repo guidance.

## Verification

- `git diff --cached --check`
- `markdownlint-cli2` on `AGENTS.md` and this change report.

## Risks And Follow-Ups

- None known.

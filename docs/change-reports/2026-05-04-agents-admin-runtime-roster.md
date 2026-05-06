# Agents Admin Runtime Roster Repair - 2026-05-04

## Issue

The dashboard showed the live OpenClaw runtime roster, but the Agents admin page showed only one provisioned database agent and marked it offline.

## Root Cause

The dashboard reads `/api/v1/gateways/runtime-overview`, which reports live gateway sessions. The Agents admin page only read `/api/v1/agents`, which is the provisioning database roster. After the OpenClaw 5.3 gateway repair, the database roster had one stale gateway agent while the live gateway reported 23 agents and 3 subagents.

## Changes Made

- Updated the Agents admin page to fetch configured gateways and their live runtime overviews.
- Merged live runtime sessions with provisioned database agents by `openclaw_session_id`.
- Converted live runtime status into admin roster status:
  - `idle`, `done`, `waiting`, `online` -> `online`
  - `working`, `busy`, `in_progress` -> `busy`
  - `broken`, `error`, `failed`, `offline` -> `offline`
- Added runtime-only rows for live agents and subagents that do not exist in the provisioning database.
- Kept edit/delete actions hidden for runtime-only rows so synthetic live-session rows cannot be accidentally modified as database agents.
- Added a focused regression test for the runtime roster merge.

## Verification

- `npx tsc --noEmit --pretty false` passed.
- `npx vitest run --passWithNoTests --coverage=false src/app/agents/page.empty-state.test.tsx src/components/agents/AgentsTable.test.tsx src/components/tables/DataTable.test.tsx` passed: 10 tests.
- `npm run build` passed.
- Restarted `openclaw-mission-control-frontend.service`.
- `GET http://127.0.0.1:3000/agents` returned 200 after restart.
- Live runtime API still reports 26 total runtime sessions: 23 agents and 3 subagents.

## Notes

- No commits were created.
- The bridge team was attempted first, but the existing dirty project worktree blocked normal team-start; a clean temporary worktree was used to start the bridge, but the worker did not receive the actual task. The failed bridge team and temporary worktree were shut down and removed.

# Mission Control UI Stabilization — 2026-04-29

## Final readiness verdict
- In progress.
- Current status: partially functional.

## Scope
Stabilize and harden Mission Control so each implemented UI surface accurately reflects runtime/config state, distinguishes empty state vs failure vs unavailable host tooling, and refreshes without misleading summaries.

## Page / surface inventory
### Core
- `/dashboard`
  - Boards summary: `/api/v1/boards`
  - DB agents summary: `/api/v1/agents`
  - KPI/task summary: `/api/v1/metrics/dashboard`
  - Recent activity: `/api/v1/activity`
  - Gateway/session summary: currently `/api/v1/gateways/status`; should be grounded by `/api/v1/gateways` for configured gateway count
- `/activity`
  - Activity feed: `/api/v1/activity`
  - Streaming surfaces also exist for board/task/approval/agent events
- `/agents`
  - DB-backed provisioning roster: `/api/v1/agents`
  - Board labels: `/api/v1/boards`
- `/gateways`
  - Configured gateways: `/api/v1/gateways`
- `/gateways/[gatewayId]`
  - Gateway config: `/api/v1/gateways/{gatewayId}`
  - Runtime/session status: `/api/v1/gateways/status`
- `/gateways/[gatewayId]/crons`
  - Cron status: `/api/v1/gateways/crons`
- `/boards`, `/board-groups`, `/approvals`, `/tags`, `/custom-fields`, `/skills/marketplace`, `/skills/packs`, `/settings`
  - Additional implemented surfaces still need explicit endpoint mapping pass in this doc

## API endpoint inventory checked in this pass
- `GET /api/v1/gateways`
- `GET /api/v1/gateways/status?gateway_url=ws://127.0.0.1:18789`
- `GET /api/v1/gateways/runtime-overview?gateway_url=ws://127.0.0.1:18789`
- `GET /api/v1/gateways/crons?gateway_url=ws://127.0.0.1:18789`
- `GET /api/v1/metrics/dashboard`
- `GET /api/v1/agents`
- `GET /api/v1/boards`
- `GET /api/v1/board-groups`
- `GET /api/v1/activity`

## Live runtime evidence
### Backend / frontend
- `GET http://127.0.0.1:8000/healthz` → `{"ok":true}`
- `GET http://127.0.0.1:8000/readyz` → `{"ok":true}`
- `HEAD http://127.0.0.1:3000` → `HTTP/1.1 200 OK`

### Ports / listeners
- `3000` listening
- `8000` listening
- `5432` listening
- `6379` listening
- `18789` listening via `openclaw-gateway`

### Processes
- frontend: `next-server (v16.1.7)`
- backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- worker: `uv run python ../scripts/rq worker`

### Containers
- `mc-db` → Up
- `mc-redis` → Up

### Gateway runtime
- `openclaw gateway status`
  - runtime: running
  - connectivity probe: ok
  - capability: admin-capable
  - listening: `0.0.0.0:18789`
- `journalctl -u openclaw-gateway -n 30`
  - no journal entries visible to current user context

### Authenticated API summaries
- `/api/v1/gateways` → status 200, items 1, total 1
- `/api/v1/boards` → status 200, items 0, total 0
- `/api/v1/board-groups` → status 200, items 0, total 0
- `/api/v1/agents` → status 200, items 1, total 1
- `/api/v1/metrics/dashboard` → status 200, KPIs all zero
- `/api/v1/activity` → status 200, items 0, total 0
- `/api/v1/gateways/status` → status 200, connected true, sessions_count 91
- `/api/v1/gateways/runtime-overview` → status 200, agents 24, subagents 10, edges 13
- `/api/v1/gateways/crons` → status 200

## Confirmed mismatch / failure findings
1. **Dashboard configured-gateway bug confirmed**
   - Runtime/API truth: one configured gateway exists.
   - Board truth: zero boards exist.
   - Previous dashboard logic inferred configured gateways only from boards with `gateway_id`.
   - Result: dashboard could claim no gateways were configured when a gateway existed but no board linked it.
2. Dashboard session summary also depended on board-linked gateway targets, so unassigned configured gateways were invisible there.
3. Focused frontend test harness for the dashboard branch is not green yet; fix is in code, but test needs additional mocking/timing cleanup.

## Changes made in this pass
### Code
- Updated `frontend/src/app/dashboard/page.tsx`
  - Dashboard now loads configured gateways from `/api/v1/gateways`.
  - Gateway target derivation now starts from configured gateways, then annotates optional linked board.
  - Gateway status polling now supports gateways without a linked board.
  - Configured gateway count now reflects actual gateway records, not board-linked subset.
  - Sessions panel empty state text changed from board-scoped wording to true configured-gateway wording.
  - Sessions panel now shows a specific notice when configured gateways are not linked to boards.

### Tests
- Added `frontend/src/app/dashboard/page.test.tsx`
  - Covers intended regression scenario in progress.
  - Currently failing due to test harness/query timing mismatch; needs follow-up.

## Task checklist
- [x] Create/update stabilization tracker doc
- [x] Re-run baseline health/runtime/API probes
- [x] Confirm dashboard configured-gateway mismatch with live evidence
- [x] Patch dashboard to use configured gateway roster
- [ ] Finish endpoint mapping for every implemented UI page
- [ ] Verify board task/approval endpoints for any configured board
- [ ] Tighten dashboard regression test until passing
- [ ] Audit additional misleading empty/error states across remaining pages
- [ ] Run broader targeted frontend/backend checks
- [ ] Final readiness pass

## Test plan
### Targeted
- `npx vitest run src/app/dashboard/page.test.tsx --coverage.enabled=false`
- additional targeted tests around dashboard gateway/session summaries if needed

### Broader
- `make frontend-test`
- `make backend-test`
- `make check` if feasible after targeted fixes are stable

## Tests run
- `npx vitest run src/app/dashboard/page.test.tsx --coverage.enabled=false`
  - status: failing
  - reason: test harness does not yet observe the new async notice branch reliably

## Files changed
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/dashboard/page.test.tsx`
- `docs/operations/mission-control-ui-stabilization-2026-04-29.md`

## Remaining risks
- The new dashboard behavior is patched but not yet backed by a passing focused test.
- Full inventory/verification of all implemented pages is still incomplete.
- Board/task/approval endpoint verification is still pending because there are currently zero boards configured.
- Some host log visibility is limited by journal permissions.

## Deferred / pending
- Complete full surface-by-surface mapping for remaining implemented pages.
- Add/repair passing regression coverage for dashboard configured-gateway visibility.
- Broader test/build sweep after targeted fixes stabilize.

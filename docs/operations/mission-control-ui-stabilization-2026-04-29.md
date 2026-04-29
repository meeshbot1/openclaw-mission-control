# Mission Control UI Stabilization — 2026-04-29

## Final readiness verdict
- In progress.
- Current status: partially functional.

## Scope
Stabilize and harden Mission Control so each implemented UI surface accurately reflects runtime/config state, distinguishes empty state vs failure vs unavailable host tooling, and refreshes without misleading summaries.

## Page / surface inventory
### Public / auth
- `/`
  - marketing shell; no Mission Control API imports
- `/sign-in/[[...rest]]`
  - sign-in shell
- `/invite`
  - organizations API
- `/onboarding`
  - users API
- `/settings`
  - users API

### Dashboard / activity
- `/dashboard`
  - `/api/v1/boards`
  - `/api/v1/agents`
  - `/api/v1/gateways`
  - `/api/v1/gateways/status`
  - `/api/v1/metrics/dashboard`
  - `/api/v1/activity`
- `/activity`
  - `/api/v1/activity`
  - `/api/v1/agents/stream`
  - `/api/v1/boards`
  - `/api/v1/boards/{boardId}/snapshot`
  - `/api/v1/boards/{boardId}/memory/stream`
  - `/api/v1/boards/{boardId}/approvals/stream`
  - `/api/v1/boards/{boardId}/tasks/stream`
  - organizations membership API

### Gateways
- `/gateways`
  - `/api/v1/gateways`
- `/gateways/new`
  - `/api/v1/gateways`
- `/gateways/[gatewayId]`
  - `/api/v1/gateways/{gatewayId}`
  - `/api/v1/gateways/status`
  - `/api/v1/gateways/crons`
  - `/api/v1/gateways/runtime-overview`
  - `/api/v1/agents?gateway_id=...`
  - `/api/v1/boards`
- `/gateways/[gatewayId]/edit`
  - `/api/v1/gateways/{gatewayId}`
- `/gateways/[gatewayId]/crons`
  - `/api/v1/gateways/{gatewayId}`
  - `/api/v1/gateways/crons`

### Agents
- `/agents`
  - `/api/v1/agents`
  - `/api/v1/boards`
- `/agents/new`
  - `/api/v1/agents`
  - `/api/v1/boards`
- `/agents/[agentId]`
  - `/api/v1/agents/{agentId}`
  - `/api/v1/activity`
  - `/api/v1/boards`
- `/agents/[agentId]/edit`
  - `/api/v1/agents/{agentId}`
  - `/api/v1/boards`

### Boards / board groups
- `/boards`
  - `/api/v1/boards`
  - `/api/v1/board-groups`
- `/boards/new`
  - `/api/v1/boards`
  - `/api/v1/board-groups`
  - `/api/v1/gateways`
- `/boards/[boardId]`
  - `/api/v1/boards/{boardId}` surfaces
  - `/api/v1/boards/{boardId}/tasks*`
  - `/api/v1/boards/{boardId}/approvals*`
  - `/api/v1/boards/{boardId}/memory*`
  - `/api/v1/activity`
  - `/api/v1/agents`
  - organizations/tags/custom-fields APIs
- `/boards/[boardId]/edit`
  - `/api/v1/boards/{boardId}`
  - `/api/v1/agents`
  - `/api/v1/board-groups`
  - `/api/v1/board-webhooks`
  - `/api/v1/gateways`
- `/boards/[boardId]/approvals`
  - board approvals surface (needs direct code read if further issues found)
- `/boards/[boardId]/webhooks/[webhookId]/payloads`
  - `/api/v1/board-webhooks`
- `/board-groups`
  - `/api/v1/board-groups`
- `/board-groups/new`
  - `/api/v1/board-groups`
  - `/api/v1/boards`
- `/board-groups/[groupId]`
  - `/api/v1/board-groups/{groupId}`
  - `/api/v1/board-group-memory`
  - organizations API
- `/board-groups/[groupId]/edit`
  - `/api/v1/board-groups/{groupId}`
  - `/api/v1/boards`

### Approvals / organization metadata
- `/approvals`
  - `/api/v1/approvals`
  - `/api/v1/boards`
- `/organization`
  - `/api/v1/organizations`
  - `/api/v1/boards`

### Tags / custom fields
- `/tags`
  - `/api/v1/tags`
- `/tags/add`
  - `/api/v1/tags`
- `/tags/[tagId]/edit`
  - `/api/v1/tags/{tagId}`
- `/custom-fields`
  - `/api/v1/org-custom-fields`
- `/custom-fields/new`
  - `/api/v1/org-custom-fields`
  - `/api/v1/boards`
- `/custom-fields/[fieldId]/edit`
  - `/api/v1/org-custom-fields/{fieldId}`
  - `/api/v1/boards`

### Skills
- `/skills`
  - minimal/no direct generated API imports in page component
- `/skills/marketplace`
  - `/api/v1/skills-marketplace`
  - `/api/v1/skills`
  - `/api/v1/gateways`
- `/skills/marketplace/new`
  - needs direct code read if issues appear
- `/skills/marketplace/[skillId]/edit`
  - needs direct code read if issues appear
- `/skills/packs`
  - `/api/v1/skills`
- `/skills/packs/new`
  - `/api/v1/skills`
- `/skills/packs/[packId]/edit`
  - `/api/v1/skills`

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
3. Dashboard regression coverage is now green for the configured-gateway/no-board case.
4. Board task/approval endpoint verification is presently blocked by real configuration state: there are zero boards, so board-scoped verification cannot proceed without creating/configuring a board.
5. Gateway detail and gateway cron pages now have focused page-level tests covering key empty/failing states, but broader runtime-path manual verification is still pending.
6. Global approvals page previously fell through to an "All clear" empty state when zero boards existed, which was misleading; it now distinguishes no-board configuration from an empty approvals queue.
7. Global agents page empty-state copy previously referenced "this board" even though the page is organization-wide; wording now matches Mission Control scope.

## Changes made in this pass
### Code
- Updated `frontend/src/app/dashboard/page.tsx`
  - Dashboard now loads configured gateways from `/api/v1/gateways`.
  - Gateway target derivation now starts from configured gateways, then annotates optional linked board.
  - Gateway status polling now supports gateways without a linked board.
  - Configured gateway count now reflects actual gateway records, not board-linked subset.
  - Sessions panel empty state text changed from board-scoped wording to true configured-gateway wording.
  - Sessions panel now shows a specific notice when configured gateways are not linked to boards.
- Updated `frontend/src/app/approvals/page.tsx`
  - Global approvals now shows a configuration-specific empty state when no boards exist.
- Updated `frontend/src/components/BoardApprovalsPanel.tsx`
  - Empty state messaging is now configurable so pages can distinguish healthy-empty vs not-configured states.
- Updated `frontend/src/app/agents/page.tsx`
  - Global empty-state copy now references Mission Control scope instead of a single board.

### Tests
- Added `frontend/src/app/dashboard/page.test.tsx`
  - Covers configured gateway present + no linked board regression scenario.
- Added `frontend/src/app/gateways/[gatewayId]/page.test.tsx`
  - Covers empty runtime-edge, empty agent-list, and empty cron-list states on gateway detail page.
- Added `frontend/src/app/gateways/[gatewayId]/crons/page.test.tsx`
  - Covers failing-cron summary and cron job detail rendering.
- Added `frontend/src/app/approvals/page.no-boards.test.tsx`
  - Covers configuration-specific empty state when zero boards exist.
- Added `frontend/src/app/agents/page.empty-state.test.tsx`
  - Covers corrected global empty-state copy.

## Task checklist
- [x] Create/update stabilization tracker doc
- [x] Re-run baseline health/runtime/API probes
- [x] Confirm dashboard configured-gateway mismatch with live evidence
- [x] Patch dashboard to use configured gateway roster
- [x] Finish endpoint mapping for implemented UI pages at route/import level
- [ ] Verify board task/approval endpoints for any configured board [blocked: no boards exist]
- [x] Tighten dashboard regression test until passing
- [ ] Audit additional misleading empty/error states across remaining pages
- [~] Audit additional misleading empty/error states across remaining pages
- [x] Add focused test coverage for gateway detail / cron pages
- [ ] Run broader targeted frontend/backend checks
- [ ] Decide and, if warranted, implement bounded Mission Control heartbeat/cron
- [ ] Final readiness pass

## Test plan
### Targeted
- `npx vitest run src/app/dashboard/page.test.tsx --coverage.enabled=false`
- `npx vitest run src/app/gateways/[gatewayId]/page.test.tsx --coverage.enabled=false`
- `npx vitest run src/app/gateways/[gatewayId]/crons/page.test.tsx --coverage.enabled=false`
- `npx vitest run src/app/approvals/page.no-boards.test.tsx --coverage.enabled=false`
- `npx vitest run src/app/agents/page.empty-state.test.tsx --coverage.enabled=false`
- additional targeted tests around dashboard gateway/session summaries if needed

### Broader
- `make frontend-test`
- `make backend-test`
- `make check` if feasible after targeted fixes are stable

## Tests run
- `npx vitest run src/app/dashboard/page.test.tsx --coverage.enabled=false`
  - status: passed
- `npx vitest run src/app/dashboard/page.test.tsx src/app/gateways/[gatewayId]/page.test.tsx src/app/gateways/[gatewayId]/crons/page.test.tsx --coverage.enabled=false`
  - status: passed
- `npx vitest run src/app/approvals/page.no-boards.test.tsx src/app/agents/page.empty-state.test.tsx src/app/dashboard/page.test.tsx src/app/gateways/[gatewayId]/page.test.tsx src/app/gateways/[gatewayId]/crons/page.test.tsx --coverage.enabled=false`
  - status: passed

## Files changed
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/dashboard/page.test.tsx`
- `frontend/src/app/gateways/[gatewayId]/page.test.tsx`
- `frontend/src/app/gateways/[gatewayId]/crons/page.test.tsx`
- `frontend/src/app/approvals/page.no-boards.test.tsx`
- `frontend/src/app/agents/page.empty-state.test.tsx`
- `frontend/src/app/approvals/page.tsx`
- `frontend/src/components/BoardApprovalsPanel.tsx`
- `frontend/src/app/agents/page.tsx`
- `docs/operations/mission-control-ui-stabilization-2026-04-29.md`

## Remaining risks
- Route/import inventory is done, but not every page has been manually exercised for runtime behavior.
- Board/task/approval endpoint verification is blocked because there are currently zero boards configured.
- Gateway detail / cron pages have focused tests, but still need broader live/manual runtime-path verification.
- Additional empty/error-state audit is still in progress across remaining pages.
- Some host log visibility is limited by journal permissions.

## Deferred / pending
- Manual/live verification sweep across remaining implemented pages.
- Broader test/build sweep after targeted fixes stabilize.

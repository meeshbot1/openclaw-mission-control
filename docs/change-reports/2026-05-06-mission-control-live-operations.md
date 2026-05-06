# Change Report: Mission Control Live Operations

Date: 2026-05-06

## High-Level Changes
- Added an admin API endpoint at `GET /api/v1/gateways/mission-control/live`.
- Added a filesystem scanner for configured gateway workspace roots and optional `MISSION_CONTROL_PROJECT_WORKSPACE_ROOTS` entries.
- Normalized OMX team sessions, task statuses, worker pane ids, mailbox messages, events, and gateway runtime agents into one response.
- Added a dashboard Live Operations section that polls every 5 seconds and shows Codex teams, task counts, active worker panes, recent team messages/events, runtime gateways, and scan roots.
- Added backend and dashboard tests for the live operations payload and UI.

## Files
- `backend/app/api/gateways.py`
- `backend/app/schemas/mission_control.py`
- `backend/app/services/openclaw/mission_control_ops_service.py`
- `backend/tests/test_mission_control_live_api.py`
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/dashboard/page.test.tsx`

## Verification
- `cd backend && uv run ruff check app/api/gateways.py app/schemas/mission_control.py app/services/openclaw/mission_control_ops_service.py tests/test_mission_control_live_api.py`
- `cd backend && uv run mypy app/api/gateways.py app/schemas/mission_control.py app/services/openclaw/mission_control_ops_service.py`
- `cd backend && uv run pytest tests/test_mission_control_live_api.py -q`
- `cd backend && uv run python -m compileall app tests/test_mission_control_live_api.py`
- `cd frontend && npm run lint -- src/app/dashboard/page.tsx src/app/dashboard/page.test.tsx`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npx vitest run src/app/dashboard/page.test.tsx`

## Notes
- `npm test -- src/app/dashboard/page.test.tsx` runs the test successfully but exits non-zero because the project script enables global 100% coverage thresholds for unrelated files. The direct Vitest command above verifies this focused test without the global coverage gate.
- Additional project roots can be added with `MISSION_CONTROL_PROJECT_WORKSPACE_ROOTS`, comma or newline separated.

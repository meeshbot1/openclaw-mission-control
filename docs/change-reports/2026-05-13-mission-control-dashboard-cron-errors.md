# Change Report: Mission Control Dashboard Cron Errors

Date: 2026-05-13
Branch: amish/mission-control-dashboard-cron-error-details-20260513
Commit scope: Dashboard drill-downs, cron run visibility, error assignment visibility, and nightly stability checks.

## High-Level Changes

- Added clickable dashboard cards with detail routing so dashboard summaries lead to focused operational views.
- Expanded gateway cron data with last run, next run, last result, and failed-run action items.
- Added a dashboard error database view that surfaces assigned agents, assigned crons, and scheduled remediation signals.
- Documented Mission Control stability requirements and added a disabled nightly stabilizer check script.
- Updated build and formatting guardrails so the normal `make check` path succeeds on this host.

## File And Section References

- `frontend/src/app/dashboard/page.tsx`: dashboard card navigation, error summary data, and detail links.
- `frontend/src/app/dashboard/details/[cardId]/page.tsx`: dashboard card details route.
- `frontend/src/app/dashboard/errors/page.tsx`: logged error database view with assignment and schedule context.
- `frontend/src/app/gateways/[gatewayId]/crons/page.tsx`: cron run timing, last result, and failure action items.
- `frontend/src/lib/gateway-crons.ts`: cron schedule/result normalization helpers.
- `backend/app/services/openclaw/mission_control_ops_service.py`: live operation payload enrichment for crons, errors, assignments, and action items.
- `backend/app/schemas/mission_control.py`: response schemas for the enriched Mission Control API payloads.
- `backend/app/api/gateways.py` and `backend/app/api/gateway.py`: gateway API response integration.
- `docs/operations/mission-control-stability-test-requirements.md`: formal stability test requirements.
- `scripts/mission-control-stability-check.py`: deterministic stabilizer check command for the disabled nightly cron.
- `frontend/next.config.ts` and `scripts/safe-frontend-build.sh`: guarded frontend production build profile.

## Verification

- `make check`
- Backend coverage: `481 passed, 1 xfailed`, 100% scoped coverage.
- Frontend tests: `40` test files and `135` tests passed, 100% configured coverage.
- Frontend production build completed and generated dashboard detail/error routes.
- Restarted Mission Control backend, frontend, RQ worker, and OpenClaw gateway services.
- Verified `http://127.0.0.1:8000/health`, `http://127.0.0.1:3000/dashboard`, and `http://127.0.0.1:18789/health`.

## Risks And Follow-Ups

- Backend tests still emit two non-failing sqlite `ResourceWarning` messages in `test_mission_control_live_api.py`.
- The stabilizer cron is intentionally kept disabled until nightly automation is explicitly enabled.

# Mission Control Stability Test Requirements

## Purpose

This document defines the evidence required to call Mission Control stable after
fixing or troubleshooting runtime, dashboard, cron, gateway, database, or logged
error issues. It is also the checklist used by the nightly Mission Control
stabilizer cron job.

## Scope

Mission Control stability covers every layer that contributes to the operator
dashboard:

- Frontend: Next.js app on the configured Mission Control port.
- Backend: FastAPI service and authenticated API routes.
- Database: Postgres connectivity, schema state, and data availability.
- Redis and workers: queue connectivity and worker/process readiness when queue
  behavior is part of the incident.
- OpenClaw gateway: local gateway health and gateway-backed runtime APIs.
- Cron scheduler: configured OpenClaw cron jobs, last run metadata, next run
  metadata, and last run result visibility.
- Logged error registry: local error database, assignment state, related cron or
  agent owner, and action items for unresolved failures.

## Session Evidence Captured On 2026-05-13

The following checks were run during the dashboard, cron, and logged-error
stabilization session and are now baseline evidence for similar work:

- Created and used a dedicated branch:
  `amish/mission-control-dashboard-cron-error-details-20260513`.
- Restarted stale app layers so verification used current branch code:
  - Frontend restarted on `http://localhost:3000`.
  - Backend restarted on `http://localhost:8000`.
  - Gateway restarted on `http://127.0.0.1:18789`.
  - Postgres and Redis were confirmed healthy.
- Applied database migrations with `cd backend && uv run alembic upgrade head`.
- Confirmed live service health:
  - `GET http://127.0.0.1:8000/healthz` returned OK.
  - `GET http://localhost:3000/dashboard` returned HTTP 200.
  - `GET http://127.0.0.1:18789/health` returned HTTP 200.
- Confirmed logged error registry backend behavior:
  - `GET /api/v1/gateways/mission-control/errors?status=open&limit=5`
    returned rows from `/home/amish/.openclaw/logs/openclaw-error-registry.db`.
  - The sampled open rows were all assigned.
  - The sampled open rows had zero missing `assigned_agent_id` values.
- Confirmed dashboard behavior:
  - Dashboard cards link to `/dashboard/details/[cardId]`.
  - A card click reached the corresponding detail page.
- Confirmed cron dashboard behavior:
  - The cron dashboard rendered live cron rows.
  - `Last run`, `Next run`, and `Result` were visible together in the cron
    table.
  - Failed-cron action item rendering was covered by frontend tests.
- Confirmed logged-error UI behavior:
  - `/dashboard/errors` rendered the error registry view.
  - Desktop and mobile layouts showed assigned agent/cron and activity state.
  - No visible `Unassigned` rows appeared in the refreshed live error view.
- Browser smoke evidence was captured:
  - `/tmp/mission-control-dashboard-detail-refreshed.png`
  - `/tmp/mission-control-errors-refreshed.png`
  - `/tmp/mission-control-crons-refreshed.png`
  - `/tmp/mission-control-errors-mobile-refreshed.png`
- A browser response trace against the refreshed stack found no 4xx or 5xx
  responses on the checked dashboard, error registry, and cron surfaces.
- Backend verification passed:
  - `uv run python -m py_compile app/schemas/mission_control.py app/services/openclaw/mission_control_ops_service.py app/api/gateways.py`
  - `uv run pytest tests/test_mission_control_live_api.py`
- Frontend verification passed:
  - `npx tsc --noEmit --pretty false`
  - targeted `npx eslint` on changed frontend files
  - `npx vitest run --passWithNoTests --maxWorkers=1 --no-file-parallelism`
    for dashboard, cron page, and cron parsing tests.

## Stability Requirements

### Layer Freshness

Before accepting a fix, prove that the tested app is not stale:

- The frontend process must be started after the relevant frontend changes are
  present on disk.
- The backend process must be started after the relevant backend changes are
  present on disk.
- The gateway process must be reachable through the configured gateway URL.
- The database migrations must be current or explicitly reported as unchanged.
- The verification report must identify the frontend, backend, gateway, DB, and
  Redis evidence used.

### Backend API Readiness

Required checks:

- `/healthz` returns HTTP 200.
- `/readyz` returns HTTP 200.
- Authenticated dashboard APIs return HTTP 200 or a documented expected empty
  state:
  - `/api/v1/metrics/dashboard`
  - `/api/v1/gateways/status`
  - `/api/v1/gateways/runtime-overview`
  - `/api/v1/gateways/crons`
  - `/api/v1/gateways/mission-control/errors`
- API failures must include the failing route, status code, and an action item.
  Reports must not print bearer tokens, gateway tokens, passwords, or full
  secret-bearing URLs.

### Frontend Readiness

Required checks:

- `/dashboard` returns HTTP 200.
- Dashboard card links exist for all dashboard summary/detail cards.
- Each detail-card URL renders a stable detail page or a documented expected
  empty state.
- `/dashboard/errors` renders a logged-error registry view.
- `/gateways/[gatewayId]/crons` renders cron metadata with `Last run`,
  `Next run`, and `Result`.
- UI surfaces must distinguish loading, empty state, unavailable runtime, and
  error state.

### Cron Dashboard Requirements

Every visible cron row must expose:

- Job name.
- Schedule and timezone.
- Enabled/disabled status.
- Owning agent.
- Model, when configured.
- Last run timestamp, when known.
- Next run timestamp, when known and applicable.
- Last run status.
- Last run result or error summary.
- Failed-run action items when a failed run included them or when they can be
  derived from the failure.

If a cron run failed, the dashboard must surface concrete action items rather
than only showing a status badge.

### Logged Error Registry Requirements

The logged error registry view must show:

- Database path or source label.
- Counts for total rows, assigned rows, working rows, and open rows.
- Status filters for open, observed, ignored, and all.
- Error level, status, category, message, source, and first/last-seen
  timestamps.
- Assigned agent ID.
- Assigned cron ID/name when a cron can be inferred.
- Assigned cron schedule, timezone, enabled state, last run, last run status,
  next run, and remediation schedule status.
- Assignment state (`working`, `assigned`, `queued`, or equivalent).
- Action items for every visible unresolved error.

Open error rows should not remain `Unassigned` when a service, gateway, cron, or
project ownership can be inferred. If an error is truly unassigned, the report
must explain why no owner could be inferred and what signal is missing.
Open error rows must also show whether remediation is actually scheduled. If the
assigned remediation cron is disabled or has no computed next run, the UI must
say that directly instead of only showing the assigned agent.

### Test And Static Verification

Required after code changes:

- Backend syntax/import smoke for changed backend modules.
- Focused backend pytest for changed API/service behavior.
- Frontend typecheck for changed TypeScript.
- Focused frontend lint for changed files.
- Focused Vitest/Testing Library coverage for changed UI/parser behavior.
- Browser smoke for user-facing layout or navigation changes.

Full `make check` is desirable for release readiness, but on this VPS it must
respect the resource guard in `AGENTS.md`. If memory is too low, the report must
state that the full build/check was deferred and list the targeted substitute
evidence.

### Definition Of Done For Mission Control Error Fixes

A Mission Control error fix is done only when:

- The root cause is identified or the remaining unknown is explicitly bounded.
- The current branch code is running in the frontend/backend process under test.
- DB migrations are applied or confirmed unnecessary.
- Frontend, backend, gateway, DB, and Redis health are all verified.
- The relevant authenticated APIs return successful responses.
- Logged errors for the incident are assigned to an agent or cron owner.
- Logged errors show when the assigned cron/agent remediation will run, or show
  an explicit not-scheduled/disabled state.
- Open failures expose action items.
- The UI no longer presents misleading `Unassigned`, stale, or partial data.
- Focused backend and frontend automated checks pass.
- Browser smoke passes for changed operator surfaces.
- The final report includes commands run, evidence, screenshots when relevant,
  remaining risks, and any checks intentionally skipped for resource safety.

## Nightly Stabilizer Expectations

The nightly stabilizer cron job must:

- Run non-destructively.
- Use this document as the checklist.
- Refresh evidence from live frontend, backend, database, Redis, gateway, cron,
  and logged-error APIs.
- Emit JSON with:
  - overall status;
  - per-check pass/fail state;
  - concise evidence;
  - action items for every failure;
  - no secrets.
- Exit non-zero when required checks fail.
- Stay disabled until explicitly enabled after review.

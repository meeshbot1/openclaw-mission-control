# Mission Control UI Tutorials And Drill-Down Report

Commit scope: Add usage documentation, screenshots, tutorial videos, and focused monitoring fixes for Mission Control live operations.

## Changes

- Removed remaining browser-side gateway-token query propagation from dashboard, agents, and cron runtime checks.
- Extended gateway session APIs so runtime session history can be resolved by `gateway_url` as well as `board_id`.
- Added gateway runtime `View logs` actions for agents and subagents with a 5-second refreshing session-history panel.
- Added cron-row `Inspect` details for last-run status, duration, schedule, and runtime target.
- Added a complete Mission Control UI tutorial with screenshots and silent MP4 walkthroughs.

## Artifacts

- `docs/tutorials/mission-control-ui.md`
- `docs/tutorials/assets/screenshots/mission-control-dashboard-live-operations.png`
- `docs/tutorials/assets/screenshots/gateway-runtime-agent-logs.png`
- `docs/tutorials/assets/screenshots/gateway-cron-inspector.png`
- `docs/tutorials/assets/videos/mission-control-dashboard-live-operations.mp4`
- `docs/tutorials/assets/videos/mission-control-gateway-drilldown.mp4`

## Issues Found And Fixed

- Cron dashboard still included `gateway_token` in browser query construction. Runtime polling now relies on backend-side credential resolution.
- Dashboard and agents runtime polling also included browser-side gateway tokens. Those query params were removed.
- Gateway runtime rows showed status but did not expose session history. `View logs` now opens the gateway session transcript panel.
- Cron rows showed status but did not expose per-row detail. `Inspect` now opens cron run metadata.

## Issues Logged

- Next.js Turbopack dev server crashed with a local persistence-cache panic during screenshot capture. Capture used `next dev --webpack`.
- The backend CORS allowlist does not permit ad-hoc frontend port `3001`; artifact capture used Chromium web-security bypass. The primary local frontend port `3000` remains the normal operator URL.
- Gateway cron APIs return run metadata, not standalone cron stdout/stderr logs. A future gateway protocol addition would be needed for separate per-run log streaming.

## Verification

- `cd backend && uv run pytest tests/test_gateway_resolver.py tests/test_mission_control_live_api.py -q`
- `cd frontend && npx eslint 'src/app/gateways/[gatewayId]/page.tsx' 'src/app/gateways/[gatewayId]/crons/page.tsx' 'src/app/dashboard/page.tsx' 'src/app/agents/page.tsx'`
- `cd frontend && npx vitest run src/app/dashboard/page.test.tsx src/app/gateways/[gatewayId]/page.test.tsx src/app/gateways/[gatewayId]/crons/page.test.tsx --coverage=false`
- Live API probes for gateway runtime overview and crons returned 29 agents, 2 subagents, 2 collaboration edges, and 2 cron jobs.
- Playwright captured dashboard, gateway runtime logs, and cron inspection screenshots against the local stack.
- FFmpeg generated MP4 tutorial clips from captured UI artifacts.

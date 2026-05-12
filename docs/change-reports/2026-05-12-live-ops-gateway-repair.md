# Change Report: Live Ops Gateway Repair

Date: 2026-05-12
Branch: amish/mission-control-live-ops-20260506
Commit scope: Preserve the current Mission Control live-ops UI work and repair local gateway connectivity after token rotation.

## High-Level Changes
- Added resilient gateway-token resolution for the local OpenClaw gateway so Mission Control can connect after gateway token rotation without relying on a browser-supplied token.
- Updated the gateway detail page source to stop sending saved gateway tokens in query parameters.
- Preserved existing live operations, loading-state, documentation, screenshot, and safe frontend build updates already present in this working tree.

## File And Section References
- `backend/app/core/config.py`: adds typed OpenClaw gateway env settings.
- `backend/app/services/openclaw/session_service.py`: resolves the local gateway token from backend env when the requested gateway URL matches the configured local gateway.
- `frontend/src/app/gateways/[gatewayId]/page.tsx`: removes gateway token propagation from runtime status, cron, and runtime-overview query construction.
- `backend/tests/test_gateway_resolver.py`: adds regression coverage for local env token fallback.
- `docs/platform/README.md` and `docs/architecture/README.md`: document the current platform architecture and operator surfaces.
- `frontend/src/components/tables/DataTable.tsx` and related table pages/components: preserve current explicit loading/refreshing UI work.

## Verification
- `cd backend && uv run pytest tests/test_gateway_resolver.py tests/test_gateway_rpc_connect_scopes.py -q`
- `cd frontend && npx eslint 'src/app/gateways/[gatewayId]/page.tsx'`
- `cd frontend && npx vitest run src/app/gateways/[gatewayId]/page.test.tsx src/app/gateways/[gatewayId]/crons/page.test.tsx --coverage=false`
- Runtime probes after backend restart:
  - `/healthz` returned 200.
  - `/readyz` returned 200.
  - Gateway status returned connected with 96 sessions.
  - Gateway runtime overview returned agent/subagent/edge data.
  - Gateway crons returned cron data.
  - Frontend `/gateways` returned 200.

## Risks And Follow-Ups
- The safe frontend build refused on this VPS because available memory was below the 2 GiB guardrail; rebuild should be run when memory headroom is available.
- Repo-wide frontend lint still has an unrelated warning in `frontend/src/app/approvals/page.no-boards.test.tsx`.
- Repo-wide `npm test` enforces a 100% global coverage gate and fails when invoked against only the focused gateway tests.

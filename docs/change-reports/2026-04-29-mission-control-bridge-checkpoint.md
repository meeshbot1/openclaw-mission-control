# Change Report: Mission Control Bridge Checkpoint

Date: 2026-04-29
Branch: master
Commit scope: Checkpoint Mission Control app and agent-contract changes so OMX team worktrees can launch from a clean leader workspace.

## High-Level Changes
- Added Mission Control project-agent instructions that require Codex bridge `team-start` for app-dev work and document readiness evidence expectations.
- Added per-agent model/provider persistence, schemas, generated frontend types, and UI controls for selecting provider/model values.
- Added gateway cron/runtime visibility surfaces, including backend schema/API support, frontend cron dashboard utilities, and gateway detail UI updates.
- Added provider-specific board bootstrap template wrappers for OpenAI, Google, Anthropic, and Ollama.
- Added local ignore rules for OpenClaw runtime/bootstrap artifacts, including OMX team state, so topic-agent local state does not keep the repo dirty.

## File And Section References
- `AGENTS.md`: Mission Control topic-agent contract, Codex bridge requirement, readiness verification rules, and project commands.
- `.gitignore`: OpenClaw local runtime files, OMX team state, local bootstrap files, memory, and SQLite data ignores.
- `backend/app/models/agents.py`, `backend/app/schemas/agents.py`, `backend/migrations/versions/c1d4f6a9b2e7_add_agent_model_provider_columns.py`: persisted model provider/name fields.
- `backend/app/api/gateway.py`, `backend/app/schemas/gateway_api.py`, `backend/app/services/openclaw/session_service.py`: gateway cron/runtime payload normalization and compatibility support.
- `backend/app/services/openclaw/constants.py`, `backend/app/services/openclaw/provisioning.py`, `backend/app/services/openclaw/provisioning_db.py`, `backend/templates/providers/**`: provider-specific bootstrap template selection.
- `frontend/src/lib/agent-models.ts`, `frontend/src/app/agents/**`, `frontend/src/components/agents/AgentsTable.tsx`: provider/model UI controls and display.
- `frontend/src/lib/gateway-crons.ts`, `frontend/src/app/gateways/[gatewayId]/page.tsx`, `frontend/src/app/gateways/[gatewayId]/crons/page.tsx`: gateway cron display and polling UI.
- `docs/operations/mission-control-ui-stabilization-2026-04-29.md`, `docs/operations/implementation-plan-2026-04-07.md`: stabilization evidence and implementation notes.

## Verification
- `cd backend && uv run pytest tests/test_agent_provisioning_utils.py tests/test_gateway_version_compat.py`
- `cd frontend && npx vitest run src/app/approvals/page.no-boards.test.tsx src/app/agents/page.empty-state.test.tsx src/app/dashboard/page.test.tsx src/app/gateways/[gatewayId]/page.test.tsx src/app/gateways/[gatewayId]/crons/page.test.tsx src/lib/gateway-crons.test.ts --coverage.enabled=false`

## Risks And Follow-Ups
- This is a local checkpoint intended to unblock OMX team worktrees; broader `make check` parity remains a follow-up for the stabilization team.
- Local root bootstrap files are intentionally ignored rather than committed, so durable project-agent behavior should remain in tracked `AGENTS.md` or shared OpenClaw agent config.

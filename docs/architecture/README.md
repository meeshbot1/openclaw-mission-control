# Architecture

Mission Control is a FastAPI + Next.js operations dashboard backed by Postgres,
Redis, and an OpenClaw gateway WebSocket connection.

For the complete current architecture, domain model, API map, runtime
integration, operations guidance, and troubleshooting notes, start with the
[Mission Control platform manual](../platform/README.md).

## High Level

- Frontend: Next.js App Router under `frontend/src/app`.
- Backend: FastAPI under `backend/app`.
- Database: Postgres via SQLModel and Alembic migrations.
- Queue/cache: Redis plus RQ worker scripts.
- Runtime integration: OpenClaw gateway WebSocket RPC, gateway session/crons APIs,
  live operations scanning, and optional local runtime visibility setup.

## Primary Flows

- Browser -> frontend -> backend REST API.
- Backend -> Postgres for durable organizations, boards, tasks, agents, approvals,
  tags, skills, webhooks, memory, and activity events.
- Backend/worker -> Redis for queued lifecycle and webhook work.
- Backend -> OpenClaw gateway for sessions, crons, runtime overview, commands,
  session history, and messages.
- Backend -> OpenClaw workspace filesystem for Mission Control live operations
  scans, team state, and Codex app-server session sidecars.

## Key References

- Platform manual: `docs/platform/README.md`
- Backend app entrypoint: `backend/app/main.py`
- Gateway session service: `backend/app/services/openclaw/session_service.py`
- Live operations service:
  `backend/app/services/openclaw/mission_control_ops_service.py`
- Runtime visibility setup: `backend/scripts/setup_runtime_visibility.py`

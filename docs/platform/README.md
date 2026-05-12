# Mission Control Platform Manual

Date: 2026-05-07
Status: living platform documentation

This document is the canonical operator and contributor overview for OpenClaw
Mission Control as it exists in this repository today. It describes what the
platform does, how the major pieces fit together, what each UI and API surface
owns, how runtime OpenClaw data enters the system, and how to develop, deploy,
verify, and troubleshoot the stack.

For focused references, also use:

- [Architecture](../architecture/README.md)
- [Getting started](../getting-started/README.md)
- [Development](../development/README.md)
- [Testing](../testing/README.md)
- [Deployment](../deployment/README.md)
- [Operations](../operations/README.md)
- [Troubleshooting](../troubleshooting/README.md)
- [Configuration reference](../reference/configuration.md)
- [Authentication reference](../reference/authentication.md)
- [API notes](../reference/api.md)
- [Gateway WebSocket protocol](../openclaw_gateway_ws.md)

## 1. Product Purpose

Mission Control is the OpenClaw operations and governance dashboard. Its job is
to make agent work visible and controllable across organizations, boards,
gateways, runtime sessions, approvals, scheduled jobs, and activity history.

The platform is designed around these operator needs:

- See what OpenClaw agents and gateway sessions are doing now.
- Organize ongoing work into board groups, boards, tasks, tags, and custom
  fields.
- Manage provisioned agents and compare them with live gateway runtime agents.
- Route sensitive state changes through approvals when board policy requires it.
- Track task, approval, agent, webhook, and memory activity in one audit feed.
- Connect to local or remote OpenClaw gateways without making every UI page talk
  directly to the gateway.
- Support both web operators and automation clients through the same FastAPI API.

Mission Control has two kinds of state:

- **System-of-record state** in Postgres: organizations, users, board groups,
  boards, tasks, agents, approvals, tags, custom fields, gateways, skills, memory,
  webhooks, and activity events.
- **Live runtime state** from OpenClaw gateway and filesystem sources: current
  sessions, cron jobs, runtime agent status, live team operations, Codex app
  server threads, mailbox messages, and recent runtime events.

Both matter. DB state powers the durable workflow UI; runtime state proves what
agents and gateway jobs are actually doing right now.

## 2. Repository Map

Top-level structure:

- `backend/`: FastAPI backend, SQLModel models, Alembic migrations, pytest suite,
  backend scripts, and gateway service adapters.
- `frontend/`: Next.js application, React pages/components, generated API client,
  frontend tests, and UI utilities.
- `docs/`: operator, developer, deployment, testing, reference, and change
  documentation.
- `scripts/`: repo-level helper scripts such as CI and Node wrapper utilities.
- `compose.yml`: local Docker stack for Postgres, Redis, backend, frontend, and
  queue worker.
- `.env.example`, `backend/.env.example`, `frontend/.env.example`: environment
  templates. Real `.env` files are local only and must not be committed.
- `screenshots/`: local UI evidence captured during recent runtime validation.

Backend layout:

- `backend/app/main.py`: FastAPI application setup, middleware, OpenAPI metadata,
  router registration, health probes, and lifespan startup.
- `backend/app/api/`: thin HTTP route modules.
- `backend/app/models/`: SQLModel table definitions.
- `backend/app/schemas/`: request and response schemas.
- `backend/app/services/`: domain logic, snapshots, lifecycle orchestration,
  OpenClaw gateway integration, queue handling, tags, webhooks, and organizations.
- `backend/app/core/`: config, auth, security headers, logging, rate limits, time,
  error handling, and token helpers.
- `backend/app/db/`: async engine/session setup, CRUD helpers, query manager, and
  pagination.
- `backend/migrations/versions/`: Alembic migration history.
- `backend/scripts/`: backend helper scripts, including runtime visibility setup.
- `backend/tests/`: pytest coverage for APIs, services, schemas, security,
  gateway integration boundaries, queue behavior, and regression cases.

Frontend layout:

- `frontend/src/app/`: Next.js App Router pages.
- `frontend/src/components/`: shared UI components, tables, forms, dashboard shell,
  board/task widgets, activity feed, skills UI, and auth UI.
- `frontend/src/lib/`: API base helpers, formatting, gateway cron normalization,
  list/delete helpers, sorting hooks, backoff, onboarding helpers, and constants.
- `frontend/src/api/generated/`: generated API client. Regenerate with
  `make api-gen`; do not edit by hand.
- `frontend/src/api/mutator.ts`: API client mutator.
- `frontend/src/setupTests.ts`: frontend test setup.

## 3. Runtime Architecture

The default local platform is:

- Browser -> Next.js frontend on `http://127.0.0.1:3000`.
- Frontend -> FastAPI backend on `http://127.0.0.1:8000`.
- Backend -> Postgres on `127.0.0.1:5432`.
- Backend/worker -> Redis on `127.0.0.1:6379`.
- Backend -> OpenClaw gateway WebSocket on `ws://127.0.0.1:18789`.
- RQ worker -> Redis queue -> backend lifecycle and webhook jobs.

Backend app startup:

1. `backend/app/main.py` configures logging.
2. CORS is enabled from configured origins.
3. security headers and error handling are installed.
4. Rate-limit backend is validated.
5. `init_db()` creates schema or runs migrations when configured.
6. Routers are mounted under `/api/v1`.
7. `/healthz` and `/readyz` are exposed for liveness and readiness checks.

Frontend app startup:

1. Next.js serves the shell, public routes, and dashboard routes.
2. `AuthProvider` resolves local or Clerk auth state.
3. `QueryProvider` supplies TanStack Query caching and polling.
4. Generated API hooks and local fetch helpers call the backend.
5. Dashboard pages render DB-backed resources and gateway-backed live panels.

Queue/runtime support:

- Redis backs job queues and rate-limit storage when configured.
- `scripts/rq worker` runs queued lifecycle and webhook work.
- OpenClaw gateway exposes session, cron, command, and message RPC methods.
- Mission Control normalizes gateway responses before presenting them to the UI.

## 4. Core Domain Model

### Organizations And Users

Organizations are the tenancy boundary for boards, board groups, members, invites,
gateways, tags, skills, and access policy. Users are attached to organizations
through membership records.

Key models:

- `Organization`: top-level tenant.
- `User`: app user profile.
- `OrganizationMember`: user's role and board access within an organization.
- `OrganizationInvite`: invitation flow.
- `OrganizationBoardAccess`: scoped board permissions.

Important routes:

- `POST /api/v1/organizations`
- `GET /api/v1/organizations/me`
- `GET /api/v1/organizations/me/list`
- `PATCH /api/v1/organizations/me/active`
- `GET /api/v1/organizations/me/member`
- `GET/PATCH/DELETE /api/v1/organizations/me/members/{member_id}`
- `GET/POST/DELETE /api/v1/organizations/me/invites`
- `POST /api/v1/organizations/invites/accept`

Frontend pages:

- `/organization`
- `/invite`
- `/settings`

### Gateways

Gateways connect Mission Control to OpenClaw runtime environments. A gateway row
stores the URL, optional token, workspace root, TLS/device-pairing controls, and
organization association.

Key model:

- `Gateway`: configured gateway endpoint and workspace root.

Important routes:

- `GET/POST /api/v1/gateways`
- `GET/PATCH/DELETE /api/v1/gateways/{gateway_id}`
- `POST /api/v1/gateways/{gateway_id}/templates/sync`
- `GET /api/v1/gateways/status`
- `GET /api/v1/gateways/sessions`
- `GET /api/v1/gateways/sessions/{session_id}`
- `GET /api/v1/gateways/sessions/{session_id}/history`
- `POST /api/v1/gateways/sessions/{session_id}/message`
- `GET /api/v1/gateways/commands`
- `GET /api/v1/gateways/crons`
- `GET /api/v1/gateways/runtime-overview`
- `GET /api/v1/gateways/mission-control/live`

Frontend pages:

- `/gateways`
- `/gateways/new`
- `/gateways/[gatewayId]`
- `/gateways/[gatewayId]/crons`

Gateway live data is queried through `GatewaySessionService` and OpenClaw RPC
helpers in `backend/app/services/openclaw/`.

### Board Groups

Board groups organize related boards and provide group-level snapshots and memory.
They are useful for project portfolios, runtime areas, cron/job surfaces, or
multi-board programs.

Key models:

- `BoardGroup`
- `BoardGroupMemory`

Important routes:

- `GET/POST /api/v1/board-groups`
- `GET/PATCH/DELETE /api/v1/board-groups/{group_id}`
- `GET /api/v1/board-groups/{group_id}/snapshot`
- `POST /api/v1/board-groups/{group_id}/heartbeat`
- `GET/POST /api/v1/board-groups/{group_id}/memory`
- `GET /api/v1/boards/{board_id}/group-memory`

Frontend pages:

- `/board-groups`
- `/board-groups/new`
- `/board-groups/[groupId]`
- `/board-groups/[groupId]/edit`

### Boards

Boards are the primary workspace unit. They group tasks, agents, memory, webhooks,
approval policy, and goal metadata.

Key model:

- `Board`

Important fields:

- `gateway_id`: gateway associated with board runtime operations.
- `board_group_id`: optional grouping relationship.
- `board_type`: currently goal-oriented by default.
- `objective`, `success_metrics`, `target_date`: goal metadata.
- `goal_confirmed`, `goal_source`: onboarding/confirmation state.
- `require_approval_for_done`: approval gate for done transitions.
- `require_review_before_done`: review gate for status policy.
- `comment_required_for_review`: comment policy for review transitions.
- `block_status_changes_with_pending_approval`: pending approval gate.
- `only_lead_can_change_status`: lead-only status policy.
- `max_agents`: board agent capacity guard.

Important routes:

- `GET/POST /api/v1/boards`
- `GET/PATCH/DELETE /api/v1/boards/{board_id}`
- `GET /api/v1/boards/{board_id}/snapshot`
- `GET /api/v1/boards/{board_id}/group-snapshot`
- `GET/POST /api/v1/boards/{board_id}/memory`
- `GET /api/v1/boards/{board_id}/memory/stream`
- `GET/POST/PATCH/DELETE /api/v1/boards/{board_id}/webhooks`
- `GET/POST /api/v1/boards/{board_id}/onboarding`

Frontend pages:

- `/boards`
- `/boards/new`
- `/boards/[boardId]`
- `/boards/[boardId]/edit`
- `/boards/[boardId]/approvals`
- `/boards/[boardId]/webhooks/[webhookId]/payloads`

### Tasks

Tasks represent work items on a board. They include workflow status, priority,
assignment, dependency metadata, tags, custom fields, and comments.

Key models:

- `Task`
- `TaskDependency`
- `TaskFingerprint`
- `TaskCustomFieldDefinition`
- `BoardTaskCustomField`
- `TaskCustomFieldValue`
- `TagAssignment`

Task statuses:

- `inbox`
- `in_progress`
- `review`
- `done`

Important routes:

- `GET /api/v1/boards/{board_id}/tasks`
- `GET /api/v1/boards/{board_id}/tasks/stream`
- `POST /api/v1/boards/{board_id}/tasks`
- `PATCH /api/v1/boards/{board_id}/tasks/{task_id}`
- `DELETE /api/v1/boards/{board_id}/tasks/{task_id}`
- `POST /api/v1/boards/{board_id}/tasks/{task_id}/comments`

There is not currently a top-level `/api/v1/tasks` route. Task APIs are
board-scoped.

Frontend task surfaces:

- Board detail task board.
- Dashboard KPI cards and recent work sections.
- Activity feed.
- Agent detail task activity.
- Approval pages.

### Agents

Mission Control distinguishes provisioned database agents from live runtime
gateway sessions.

DB-backed agents:

- Managed through `/api/v1/agents`.
- Persist board assignment, gateway link, lifecycle metadata, model selection,
  identity profile/templates, heartbeat config, check-in metadata, and token hash.
- Used for create/edit/delete and agent lifecycle workflows.

Live runtime agents:

- Read from `/api/v1/gateways/runtime-overview`.
- Normalized from OpenClaw gateway `sessions.list`.
- Show live status, session key, model, channel, working-on text, subagent state,
  parent/child relationships, and collaboration edges.

Important DB agent routes:

- `GET/POST /api/v1/agents`
- `GET /api/v1/agents/stream`
- `GET/PATCH/DELETE /api/v1/agents/{agent_id}`
- `POST /api/v1/agents/{agent_id}/heartbeat`
- `POST /api/v1/agents/heartbeat`

Agent-scoped API:

- Prefix: `/api/v1/agent`
- Requires `X-Agent-Token`.
- Used by lead, worker, and gateway-main agent workflows.
- Supports board context, task work, comments, approvals, memory, heartbeat,
  delegation, and coordination endpoints.

Frontend pages:

- `/agents`
- `/agents/new`
- `/agents/[agentId]`
- `/agents/[agentId]/edit`

### Approvals

Approvals gate sensitive task transitions or operator/agent actions. Approval
records can be linked to tasks and surfaced globally or per board.

Key models:

- `Approval`
- `ApprovalTaskLink`

Important routes:

- `GET/POST /api/v1/boards/{board_id}/approvals`
- `GET /api/v1/boards/{board_id}/approvals/stream`
- `PATCH /api/v1/boards/{board_id}/approvals/{approval_id}`

Frontend pages:

- `/approvals`
- `/boards/[boardId]/approvals`

### Activity And Memory

Activity events form the operator audit trail. Memory records hold board or
board-group context, including chat-like entries and durable notes.

Key models:

- `ActivityEvent`
- `BoardMemory`
- `BoardGroupMemory`

Important routes:

- `GET /api/v1/activity`
- `GET /api/v1/activity/stream`
- `GET /api/v1/activity/task-comments/stream`
- `GET/POST /api/v1/boards/{board_id}/memory`
- `GET /api/v1/boards/{board_id}/memory/stream`
- `GET/POST /api/v1/board-groups/{group_id}/memory`
- `GET/POST /api/v1/boards/{board_id}/group-memory`

Frontend pages:

- `/activity`
- board detail memory/chat surfaces
- board group detail memory/group context surfaces

### Tags And Custom Fields

Tags provide organization-level labels for tasks. Custom fields define
organization-specific task metadata and can be bound to boards.

Key models:

- `Tag`
- `TagAssignment`
- `TaskCustomFieldDefinition`
- `BoardTaskCustomField`
- `TaskCustomFieldValue`

Important routes:

- `GET/POST /api/v1/tags`
- `GET/PATCH/DELETE /api/v1/tags/{tag_id}`
- `GET/POST /api/v1/organizations/me/custom-fields`
- `PATCH/DELETE /api/v1/organizations/me/custom-fields/{field_id}`

Frontend pages:

- `/tags`
- `/tags/add`
- `/custom-fields`
- `/custom-fields/new`
- `/custom-fields/[fieldId]/edit`

### Skills And Souls

Mission Control has an API-backed skills marketplace and skill-pack management
surface. It also exposes a souls directory lookup surface for agent templates.

Key models:

- marketplace and installed skill models in `backend/app/models/skills.py`

Important routes:

- `GET/POST /api/v1/skills/marketplace`
- `DELETE /api/v1/skills/marketplace/{skill_id}`
- `POST /api/v1/skills/marketplace/{skill_id}/install`
- `POST /api/v1/skills/marketplace/{skill_id}/uninstall`
- `GET/POST /api/v1/skills/packs`
- `GET/PATCH/DELETE /api/v1/skills/packs/{pack_id}`
- `POST /api/v1/skills/packs/{pack_id}/sync`
- `GET /api/v1/souls-directory/search`
- `GET /api/v1/souls-directory/{handle}/{slug}`

Frontend pages:

- `/skills`
- `/skills/marketplace`
- `/skills/packs`

## 5. Dashboard And UI Surfaces

The dashboard (`/dashboard`) combines:

- DB-backed board and task metrics.
- Board list and recent work.
- Gateway status and cron snapshots.
- Live Operations from `/api/v1/gateways/mission-control/live`.
- Runtime session summaries.
- Codex app-server session monitor from OpenClaw sidecar/session files.
- Pending approvals.

Other major UI surfaces:

- `/`: landing/auth entry.
- `/onboarding`: post-auth setup routing.
- `/dashboard`: operator overview.
- `/activity`: audit and event feed across boards.
- `/agents`: provisioned agents plus live runtime roster context.
- `/boards`: board directory.
- `/board-groups`: grouped workspaces.
- `/approvals`: global approval queue.
- `/gateways`: gateway configuration and runtime probes.
- `/organization`: members, invites, and access scopes.
- `/skills`, `/skills/marketplace`, `/skills/packs`: skills operations.
- `/tags`: tag catalog.
- `/custom-fields`: organization task metadata configuration.
- `/settings`: user/app settings.

The UI is built from reusable table, form, layout, and dashboard components under
`frontend/src/components/`. API access uses generated hooks where available, with
small hand-written fetchers for gateway/live endpoints that are not generated or
need query normalization.

## 6. API Surface Summary

All application routes are under `/api/v1` except health probes.

Health:

- `GET /healthz`
- `GET /readyz`

Authentication:

- `POST /api/v1/auth/bootstrap`

Core admin/operator prefixes:

- `/api/v1/activity`
- `/api/v1/agents`
- `/api/v1/approvals` through board-scoped routes
- `/api/v1/board-groups`
- `/api/v1/boards`
- `/api/v1/gateways`
- `/api/v1/metrics`
- `/api/v1/organizations`
- `/api/v1/skills`
- `/api/v1/souls-directory`
- `/api/v1/tags`
- `/api/v1/users`

Agent prefix:

- `/api/v1/agent`

OpenAPI:

- The backend customizes OpenAPI tags, descriptions, examples, and response
  descriptions in `backend/app/main.py`.
- Regenerate the frontend API client with `make api-gen` after API schema changes.

## 7. Authentication And Authorization

Mission Control supports:

- `local` auth mode: shared bearer token, useful for self-hosted/local operation.
- `clerk` auth mode: Clerk JWT-based user auth.
- Agent token auth through `X-Agent-Token` for `/api/v1/agent` endpoints.

Important auth files:

- `backend/app/core/auth.py`
- `backend/app/core/auth_mode.py`
- `backend/app/core/agent_auth.py`
- `backend/app/core/agent_tokens.py`
- `frontend/src/components/providers/AuthProvider.tsx`
- `frontend/src/components/organisms/LocalAuthLogin.tsx`
- `frontend/src/auth/`

Authorization concepts:

- Organization membership controls access to organization resources.
- Admin-only dependencies protect configuration and destructive operations.
- Board access scopes control read/write visibility.
- Agent-scoped endpoints enforce agent board access and lead/worker policies.
- Gateway-main control workflows are separated from board lead and worker
  workflows.

## 8. Gateway And Runtime Integration

Mission Control integrates with OpenClaw through:

- Gateway configuration rows in Postgres.
- Gateway WebSocket RPC helpers in `backend/app/services/openclaw/gateway_rpc.py`.
- Gateway resolution in `backend/app/services/openclaw/gateway_resolver.py`.
- Session, cron, command, history, and message APIs in
  `backend/app/services/openclaw/session_service.py`.
- Agent lifecycle/provisioning services under `backend/app/services/openclaw/`.
- Live operations scanning in
  `backend/app/services/openclaw/mission_control_ops_service.py`.

Important gateway API behaviors:

- If `.env` contains an HTTP-style gateway URL, UI/API callers should normalize it
  to WebSocket form for gateway RPC calls, for example
  `http://127.0.0.1:18789` -> `ws://127.0.0.1:18789`.
- Gateway proxy endpoints can accept `gateway_url`, `gateway_token`,
  `gateway_disable_device_pairing`, and `gateway_allow_insecure_tls` query
  parameters.
- `/api/v1/agents` is the provisioning DB roster.
- `/api/v1/gateways/runtime-overview` is the live runtime roster.
- `/api/v1/gateways/mission-control/live` aggregates Mission Control-specific
  operations data, including team operations, gateway runtime status, scan roots,
  and Codex app-server sessions.

## 9. Runtime Visibility Setup

Recent local stabilization added `backend/scripts/setup_runtime_visibility.py`.

Purpose:

- The live gateway had real runtime sessions and cron jobs, but DB-backed pages
  had no board groups, boards, or tasks.
- The setup script creates idempotent DB records that mirror current OpenClaw
  runtime state so all UIs have meaningful operational data.

What it creates or updates:

- Board groups:
  - `OpenClaw Runtime`
  - `Project Workspaces`
  - `Gateway Cron Jobs`
- Boards:
  - `Mission Control Dashboard`
  - `OpenClaw Runtime`
  - `Runtime Operations`
  - `Gateway Cron Jobs`
  - one project workspace board per directory under
    `/home/amish/.openclaw/workspace/projects`
- Agents:
  - one DB agent per live gateway runtime session key.
- Tasks:
  - one task per runtime session.
  - one task per gateway cron entry.
  - one task per project workspace.

Run:

```bash
cd backend
uv run python scripts/setup_runtime_visibility.py
```

The script is local/runtime-oriented. It is useful for the current OpenClaw
workspace and for operator visibility, but it is not a substitute for a future
productized runtime sync service with explicit scheduling, conflict policy, and
audit controls.

## 10. Local Development

Install dependencies:

```bash
make setup
```

Fast local loop:

```bash
docker compose -f compose.yml --env-file .env up -d db redis
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```

Useful URLs:

- Frontend: `http://127.0.0.1:3000`
- Backend health: `http://127.0.0.1:8000/healthz`
- Backend readiness: `http://127.0.0.1:8000/readyz`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Regenerate API client:

```bash
make api-gen
```

Run the full check suite:

```bash
make check
```

Targeted checks:

```bash
make backend-test
make backend-coverage
make frontend-test
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd frontend && npm run lint
cd frontend && npm run build
```

## 11. Deployment

Docker path:

```bash
docker compose -f compose.yml --env-file .env up -d --build
```

Systemd path:

- Backend unit: `docs/deployment/systemd/openclaw-mission-control-backend.service`
- Frontend unit: `docs/deployment/systemd/openclaw-mission-control-frontend.service`
- RQ worker unit: `docs/deployment/systemd/openclaw-mission-control-rq-worker.service`

Typical service names in this environment:

- `openclaw-mission-control-backend.service`
- `openclaw-mission-control-frontend.service`
- `openclaw-mission-control-rq-worker.service`
- `openclaw-gateway.service`

Readiness dependencies:

- Postgres reachable.
- Redis reachable when queue/rate-limit features need it.
- Backend health/readiness are `200`.
- Frontend serves `http://127.0.0.1:3000`.
- RQ worker is running for queued lifecycle/webhook work.
- Gateway WebSocket endpoint responds for live runtime pages.

## 12. Operational Readiness Checks

Minimum local readiness check:

```bash
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8000/readyz
curl -sS http://127.0.0.1:3000
```

System process/listener check:

```bash
systemctl --user status openclaw-mission-control-backend.service --no-pager -l
systemctl --user status openclaw-mission-control-frontend.service --no-pager -l
systemctl --user status openclaw-mission-control-rq-worker.service --no-pager -l
ss -ltnp | rg ':3000|:8000|:5432|:6379|:18789'
```

Gateway runtime evidence:

```bash
curl -sS -G \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  --data-urlencode "gateway_url=ws://127.0.0.1:18789" \
  --data-urlencode "gateway_token=$OPENCLAW_GATEWAY_TOKEN" \
  http://127.0.0.1:8000/api/v1/gateways/runtime-overview
```

Gateway cron evidence:

```bash
curl -sS -G \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  --data-urlencode "gateway_url=ws://127.0.0.1:18789" \
  --data-urlencode "gateway_token=$OPENCLAW_GATEWAY_TOKEN" \
  http://127.0.0.1:8000/api/v1/gateways/crons
```

Dashboard data evidence:

```bash
curl -sS \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/metrics/dashboard

curl -sS \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/boards

curl -sS \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/board-groups

curl -sS \
  -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/agents
```

## 13. Testing Strategy

Backend tests cover:

- API row behavior.
- agent auth and token lookup.
- agent creation/deletion/provisioning/lifecycle.
- approvals and task links.
- board and board group policy.
- gateway resolution/RPC/connect scopes/version compatibility.
- metrics filters/KPIs/ranges.
- Mission Control live operations payloads.
- organization services.
- queue and worker behavior.
- security headers, rate limits, and request IDs.
- task dependencies, status gates, comments, tags, and custom fields.
- webhook dispatch.

Frontend tests cover:

- dashboard behavior.
- empty states for activity/approvals/agents.
- task cards and task board interactions.
- data tables and cell formatters.
- gateway cron normalization.
- forms for skills/custom fields/gateways/tags.
- auth redirects and user menu behavior.

Run focused examples:

```bash
cd backend
uv run pytest tests/test_mission_control_live_api.py
```

```bash
cd frontend
npx vitest run src/app/dashboard/page.test.tsx --coverage.enabled=false
```

For rendered validation, use Playwright against the running frontend and check:

- body is nonblank.
- no framework error overlay is visible.
- console/page errors are absent or understood.
- `/dashboard`, `/boards`, `/board-groups`, `/agents`, `/activity`,
  `/approvals`, `/gateways`, `/organization`, and `/skills/marketplace` render
  with expected data.

## 14. Troubleshooting

### Backend Restart Loop

Symptom:

- `openclaw-mission-control-backend.service` repeatedly restarts.
- Journal shows `error while attempting to bind on address ('0.0.0.0', 8000):
  address already in use`.

Cause:

- An orphaned/manual `uvicorn app.main:app --port 8000` process owns the port
  while systemd tries to start another backend.

Check:

```bash
ss -ltnp | rg ':8000'
ps -eo pid,ppid,stat,etime,cmd | rg 'uvicorn app.main'
journalctl --user -u openclaw-mission-control-backend.service --since '30 minutes ago' --no-pager
```

Fix:

```bash
kill -TERM <orphan-parent-pid>
systemctl --user restart openclaw-mission-control-backend.service
systemctl --user status openclaw-mission-control-backend.service --no-pager -l
```

### Frontend Port Conflict

Symptom:

- systemd frontend service exits, or `next start` cannot bind port `3000`.

Cause:

- A leftover `next dev` or `next-server` process owns port `3000`.

Check:

```bash
ss -ltnp | rg ':3000'
ps -eo pid,ppid,stat,etime,cmd | rg 'next dev|next-server|npm run start'
```

Fix:

```bash
kill -TERM <leftover-next-pid>
systemctl --user restart openclaw-mission-control-frontend.service
```

### UI Shows Agents But No Boards Or Tasks

Symptom:

- The dashboard or agents page shows runtime agent counts.
- Board, task, project, approval, or activity pages look empty.

Cause:

- Gateway runtime has live sessions, but DB-backed Mission Control resources have
  not been configured or synced.

Fix for current local environment:

```bash
cd backend
uv run python scripts/setup_runtime_visibility.py
```

Then verify:

```bash
curl -sS -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/boards
curl -sS -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/board-groups
curl -sS -H "Authorization: Bearer $LOCAL_AUTH_TOKEN" \
  http://127.0.0.1:8000/api/v1/agents
```

### Compose Is Unavailable

Some hosts do not have Docker Compose v2 installed. If `docker compose` fails
with Docker CLI help or `docker: 'compose' is not a docker command`, use direct
evidence instead:

```bash
docker ps
ss -ltnp | rg ':3000|:8000|:5432|:6379|:18789'
ps -eo pid,ppid,stat,etime,cmd | rg 'uvicorn app.main|next-server|rq worker|gateway'
```

### Gateway Runtime Calls Fail

Check:

- Gateway URL is WebSocket form: `ws://127.0.0.1:18789`.
- Token is passed as `gateway_token` or configured on the gateway row.
- `openclaw-gateway.service` is running.
- Gateway listener exists on port `18789`.
- `OPENCLAW_GATEWAY_TOKEN` is present locally but never printed in logs or docs.

## 15. Known Limitations

- There is no top-level `/api/v1/tasks` route; task routes are board-scoped.
- There is no top-level `/api/v1/projects` route; project visibility is currently
  represented through board groups/boards and the local runtime visibility setup.
- Runtime visibility setup is a local helper script, not a durable sync daemon.
- `/api/v1/agents` and `/api/v1/gateways/runtime-overview` answer different
  questions. Do not compare them as if they are the same roster.
- Full end-to-end Playwright coverage is not yet a committed test suite.
- Some live operations depend on local OpenClaw filesystem layout and gateway
  sidecar/session files.
- Generated API client files must be regenerated after backend schema changes.

## 16. Change Discipline

When changing Mission Control:

- Keep generated API client changes behind `make api-gen`.
- Add or update backend tests when API behavior changes.
- Add or update frontend tests when UI behavior changes.
- Use focused Playwright validation for visual/runtime UI changes.
- Do not commit secrets or real `.env` values.
- Document operator-facing changes in `docs/change-reports/`.
- Keep runtime fixes tied to evidence: health probes, service status, API probes,
  tests, screenshots, or logs.

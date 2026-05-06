# ruff: noqa: INP001
"""Integration tests for the live Mission Control operations endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_org_admin
from app.api.gateways import router as gateways_router
from app.db.session import get_session
from app.models.gateways import Gateway
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.schemas.gateway_api import GatewayRuntimeOverviewResponse, GatewayRuntimeSessionStatus
from app.services.openclaw.session_service import GatewaySessionService
from app.services.organizations import OrganizationContext


async def _make_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


def _build_test_app(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    organization: Organization,
) -> FastAPI:
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(gateways_router)
    app.include_router(api_v1)

    async def _override_get_session() -> AsyncSession:
        async with session_maker() as session:
            yield session

    async def _override_require_org_admin() -> OrganizationContext:
        return OrganizationContext(
            organization=organization,
            member=OrganizationMember(
                organization_id=organization.id,
                user_id=uuid4(),
                role="owner",
                all_boards_read=True,
                all_boards_write=True,
            ),
        )

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[require_org_admin] = _override_require_org_admin
    return app


async def _seed_base(
    session: AsyncSession,
    *,
    workspace_root: str,
) -> tuple[Organization, Gateway]:
    organization = Organization(id=uuid4(), name="Org One")
    gateway = Gateway(
        id=uuid4(),
        organization_id=organization.id,
        name="Gateway One",
        url="https://gateway.example.local",
        workspace_root=workspace_root,
    )
    session.add(organization)
    session.add(gateway)
    await session.commit()
    return organization, gateway


def _write_team_state(
    root: Path,
    *,
    team_name: str,
    worker_name: str,
    message_body: str,
    worker_state: str = "busy",
) -> None:
    team_root = root / ".omx" / "state" / "team" / team_name
    (team_root / "tasks").mkdir(parents=True, exist_ok=True)
    (team_root / "workers" / worker_name).mkdir(parents=True, exist_ok=True)
    (team_root / "mailbox").mkdir(parents=True, exist_ok=True)
    (team_root / "events").mkdir(parents=True, exist_ok=True)
    (team_root / "config.json").write_text(
        json.dumps(
            {
                "name": team_name,
                "task": "Investigate runtime health",
                "leader_cwd": str(root),
            }
        ),
        encoding="utf-8",
    )
    (team_root / "monitor-snapshot.json").write_text(
        json.dumps(
            {
                "workerStateByName": {worker_name: worker_state},
                "workerTaskIdByName": {worker_name: "1"},
                "workerAliveByName": {worker_name: True},
            }
        ),
        encoding="utf-8",
    )
    (team_root / "tasks" / "task-1.json").write_text(
        json.dumps(
            {
                "id": "1",
                "subject": "Scan logs",
                "status": "in_progress",
                "owner": worker_name,
                "role": "executor",
            }
        ),
        encoding="utf-8",
    )
    (team_root / "workers" / worker_name / "identity.json").write_text(
        json.dumps(
            {
                "name": worker_name,
                "role": "executor",
                "pane_id": "%42",
            }
        ),
        encoding="utf-8",
    )
    (team_root / "workers" / worker_name / "status.json").write_text(
        json.dumps(
            {
                "state": worker_state,
                "updated_at": "2026-05-06T01:11:00Z",
            }
        ),
        encoding="utf-8",
    )
    (team_root / "mailbox" / "leader-fixed.json").write_text(
        json.dumps(
            {
                "worker": "leader-fixed",
                "messages": [
                    {
                        "message_id": "msg-1",
                        "from_worker": worker_name,
                        "to_worker": "leader-fixed",
                        "body": message_body,
                        "created_at": "2026-05-06T01:12:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (team_root / "events" / "events.ndjson").write_text(
        json.dumps(
            {
                "event_id": "evt-1",
                "type": "message_received",
                "worker": "leader-fixed",
                "message_id": "msg-1",
                "created_at": "2026-05-06T01:12:01Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_mission_control_live_operations_returns_team_and_gateway_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    engine = await _make_engine()
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    gateway_root = tmp_path / "gateway-workspace"
    gateway_root.mkdir()
    extra_project_root = tmp_path / "project-workspace"
    extra_project_root.mkdir()
    _write_team_state(
        gateway_root,
        team_name="gateway-team",
        worker_name="worker-1",
        message_body="Gateway runtime issue acknowledged",
    )
    _write_team_state(
        extra_project_root,
        team_name="project-team",
        worker_name="worker-2",
        message_body="Project scan complete",
        worker_state="working",
    )

    try:
        async with session_maker() as session:
            organization, gateway = await _seed_base(session, workspace_root=str(gateway_root))

        app = _build_test_app(session_maker, organization=organization)

        monkeypatch.setenv("MISSION_CONTROL_PROJECT_WORKSPACE_ROOTS", str(extra_project_root))

        async def _fake_get_runtime_overview(
            self: GatewaySessionService,
            *,
            params: object,
            organization_id: object,
            user: object,
        ) -> GatewayRuntimeOverviewResponse:
            del self, params, organization_id, user
            return GatewayRuntimeOverviewResponse(
                generated_at_ms=1778029776452,
                summary={"agents_total": 1, "subagents_total": 0, "working": 1},
                agents=[
                    GatewayRuntimeSessionStatus(
                        agent_id="mc-gateway-agent",
                        session_key=f"agent:{gateway.id}:main",
                        status="working",
                        working_on="Watching team health",
                    )
                ],
                subagents=[],
                edges=[],
            )

        monkeypatch.setattr(
            GatewaySessionService,
            "get_runtime_overview",
            _fake_get_runtime_overview,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/gateways/mission-control/live")

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["teams_total"] == 2
        assert body["summary"]["workers_active"] == 2
        assert body["summary"]["gateways_total"] == 1
        assert set(body["scanned_roots"]) == {str(gateway_root), str(extra_project_root)}
        team_names = {team["team_name"] for team in body["teams"]}
        assert team_names == {"gateway-team", "project-team"}
        gateway_team = next(team for team in body["teams"] if team["team_name"] == "gateway-team")
        assert gateway_team["task_counts"]["in_progress"] == 1
        assert gateway_team["workers"][0]["state"] == "busy"
        assert gateway_team["recent_messages"][0]["body"] == "Gateway runtime issue acknowledged"
        assert gateway_team["recent_events"][0]["type"] == "message_received"

        gateway_runtime = body["gateways"][0]
        assert gateway_runtime["gateway_id"] == str(gateway.id)
        assert gateway_runtime["ok"] is True
        assert gateway_runtime["summary"]["agents_total"] == 1
        assert gateway_runtime["agents"][0]["working_on"] == "Watching team health"
    finally:
        monkeypatch.delenv("MISSION_CONTROL_PROJECT_WORKSPACE_ROOTS", raising=False)
        await engine.dispose()

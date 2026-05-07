"""Populate Mission Control DB views from the live local OpenClaw runtime.

The dashboard has live gateway panels, but the board/group/task/agent pages are
DB-backed. This script creates idempotent records that mirror the configured
gateway runtime so the broader UI has useful operational data.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:80] or "runtime"


def _task_status(runtime_status: str | None) -> str:
    if runtime_status == "working":
        return "in_progress"
    if runtime_status in {"broken", "waiting"}:
        return "review"
    return "inbox"


def _agent_name(agent_id: str, working_on: str | None) -> str:
    if working_on and working_on.startswith("Dev Projects"):
        topic_match = re.search(r"topic:(\d+)", working_on)
        if topic_match:
            return f"Dev Projects Topic {topic_match.group(1)}"
    if agent_id.startswith("codex-proxy-mission-control"):
        return "Mission Control Dashboard Agent"
    return agent_id.replace("-", " ").replace("_", " ").title()


def _board_key(agent_id: str, session_key: str, working_on: str | None) -> str:
    text = " ".join(value for value in [agent_id, session_key, working_on or ""] if value)
    if "mission-control" in text or "topic:3" in text:
        return "mission-control-dashboard"
    if ":cron:" in session_key or (working_on or "").startswith("Cron:"):
        return "gateway-cron-jobs"
    if text.startswith("ops ") or "agent:ops:" in text:
        return "runtime-operations"
    return "openclaw-runtime"


async def run() -> None:
    from app.core.time import utcnow
    from app.db.session import async_session_maker
    from app.models.agents import Agent
    from app.models.board_groups import BoardGroup
    from app.models.boards import Board
    from app.models.gateways import Gateway
    from app.models.organizations import Organization
    from app.models.tasks import Task
    from app.schemas.gateway_api import GatewayResolveQuery
    from app.services.openclaw.session_service import GatewaySessionService

    async with async_session_maker() as session:
        organization = (await session.exec(select(Organization).order_by(Organization.created_at))).first()
        if organization is None:
            organization = Organization(name="Personal")
            session.add(organization)
            await session.flush()

        gateway = (await session.exec(select(Gateway).order_by(Gateway.created_at))).first()
        if gateway is None:
            gateway = Gateway(
                organization_id=organization.id,
                name="Local OpenClaw Gateway",
                url="ws://127.0.0.1:18789",
                workspace_root="/home/amish/.openclaw",
            )
            session.add(gateway)
            await session.flush()

        async def ensure_group(slug: str, name: str, description: str) -> BoardGroup:
            item = (
                await session.exec(
                    select(BoardGroup).where(
                        col(BoardGroup.organization_id) == organization.id,
                        col(BoardGroup.slug) == slug,
                    )
                )
            ).first()
            if item is None:
                item = BoardGroup(
                    organization_id=organization.id,
                    slug=slug,
                    name=name,
                    description=description,
                )
                session.add(item)
            else:
                item.name = name
                item.description = description
                item.updated_at = utcnow()
            await session.flush()
            return item

        groups = {
            "runtime": await ensure_group(
                "openclaw-runtime",
                "OpenClaw Runtime",
                "Live gateway agents, health, and active sessions.",
            ),
            "projects": await ensure_group(
                "project-workspaces",
                "Project Workspaces",
                "Known OpenClaw project workspaces and project-topic surfaces.",
            ),
            "crons": await ensure_group(
                "gateway-cron-jobs",
                "Gateway Cron Jobs",
                "Scheduled gateway automation and maintenance jobs.",
            ),
        }

        board_specs = {
            "mission-control-dashboard": (
                "Mission Control Dashboard",
                groups["projects"],
                "Stabilize the operations dashboard and keep it connected to live OpenClaw state.",
            ),
            "openclaw-runtime": (
                "OpenClaw Runtime",
                groups["runtime"],
                "Monitor active agents, sessions, and gateway state.",
            ),
            "runtime-operations": (
                "Runtime Operations",
                groups["runtime"],
                "Track gateway health, incidents, and operational upkeep.",
            ),
            "gateway-cron-jobs": (
                "Gateway Cron Jobs",
                groups["crons"],
                "Track scheduled gateway automation and recent cron outcomes.",
            ),
        }

        workspace_root = Path("/home/amish/.openclaw/workspace/projects")
        if workspace_root.is_dir():
            for project_dir in sorted(path for path in workspace_root.iterdir() if path.is_dir()):
                key = f"project-{_slug(project_dir.name)}"
                board_specs.setdefault(
                    key,
                    (
                        project_dir.name.replace("-", " ").title(),
                        groups["projects"],
                        f"Project workspace at {project_dir}.",
                    ),
                )

        async def ensure_board(slug: str, name: str, group: BoardGroup, objective: str) -> Board:
            item = (
                await session.exec(
                    select(Board).where(
                        col(Board.organization_id) == organization.id,
                        col(Board.slug) == slug,
                    )
                )
            ).first()
            if item is None:
                item = Board(
                    organization_id=organization.id,
                    slug=slug,
                    name=name,
                    description=objective,
                    gateway_id=gateway.id,
                    board_group_id=group.id,
                    board_type="goal",
                    objective=objective,
                    success_metrics={"runtime_visible": True},
                    goal_confirmed=True,
                    goal_source="runtime-visibility-setup",
                    max_agents=50,
                )
                session.add(item)
            else:
                item.name = name
                item.description = objective
                item.gateway_id = gateway.id
                item.board_group_id = group.id
                item.objective = objective
                item.success_metrics = {"runtime_visible": True}
                item.goal_confirmed = True
                item.max_agents = max(item.max_agents, 50)
                item.updated_at = utcnow()
            await session.flush()
            return item

        boards = {
            key: await ensure_board(key, name, group, objective)
            for key, (name, group, objective) in board_specs.items()
        }

        service = GatewaySessionService(session)
        params = GatewayResolveQuery(gateway_url=gateway.url, gateway_token=gateway.token)
        overview = await service.get_runtime_overview(
            params=params,
            organization_id=organization.id,
            user=None,
        )
        crons = await service.get_crons(params=params, organization_id=organization.id, user=None)

        async def ensure_agent(
            *,
            session_key: str,
            agent_id: str,
            status: str,
            working_on: str | None,
            board: Board | None,
        ) -> Agent:
            item = (
                await session.exec(
                    select(Agent).where(col(Agent.openclaw_session_id) == session_key)
                )
            ).first()
            name = _agent_name(agent_id, working_on)
            if item is None:
                item = Agent(
                    gateway_id=gateway.id,
                    board_id=board.id if board else None,
                    name=name,
                    status=status,
                    openclaw_session_id=session_key,
                    identity_profile={
                        "role": "Runtime Agent",
                        "communication_style": "direct, concise, practical",
                    },
                )
                session.add(item)
            else:
                item.gateway_id = gateway.id
                item.board_id = board.id if board else item.board_id
                item.name = name
                item.status = status
                item.last_seen_at = utcnow()
                item.updated_at = utcnow()
            await session.flush()
            return item

        async def ensure_task(
            *,
            reason: str,
            board: Board,
            title: str,
            description: str,
            status: str,
            assigned_agent_id: Any | None = None,
        ) -> Task:
            item = (
                await session.exec(
                    select(Task).where(
                        col(Task.auto_reason) == reason,
                    )
                )
            ).first()
            if item is None:
                item = Task(
                    board_id=board.id,
                    title=title,
                    description=description,
                    status=status,
                    priority="medium",
                    assigned_agent_id=assigned_agent_id,
                    auto_created=True,
                    auto_reason=reason,
                )
                session.add(item)
            else:
                item.board_id = board.id
                item.title = title
                item.description = description
                item.status = status
                item.assigned_agent_id = assigned_agent_id
                item.updated_at = utcnow()
            await session.flush()
            return item

        runtime_rows = [*overview.agents, *overview.subagents]
        for row in runtime_rows:
            board = boards[_board_key(row.agent_id, row.session_key, row.working_on)]
            agent = await ensure_agent(
                session_key=row.session_key,
                agent_id=row.agent_id,
                status=row.status,
                working_on=row.working_on,
                board=board,
            )
            await ensure_task(
                reason=f"runtime-session:{row.session_key}",
                board=board,
                title=f"{agent.name}: {row.working_on or row.status}",
                description=(
                    f"Live gateway session {row.session_key}\n"
                    f"Status: {row.status}\n"
                    f"Model: {row.model_provider or 'unknown'}/{row.model or 'unknown'}"
                ),
                status=_task_status(row.status),
                assigned_agent_id=agent.id,
            )

        for cron in crons.crons:
            if not isinstance(cron, dict):
                continue
            cron_id = str(cron.get("id") or cron.get("name") or "unknown")
            name = str(cron.get("name") or cron_id)
            state = cron.get("state") if isinstance(cron.get("state"), dict) else {}
            last_status = str(state.get("lastRunStatus") or state.get("lastStatus") or "scheduled")
            status = "done" if last_status == "ok" else ("review" if last_status == "error" else "inbox")
            await ensure_task(
                reason=f"runtime-cron:{cron_id}",
                board=boards["gateway-cron-jobs"],
                title=f"Cron: {name}",
                description=str(cron.get("description") or f"Gateway cron {cron_id}"),
                status=status,
            )

        for key, board in boards.items():
            if not key.startswith("project-"):
                continue
            await ensure_task(
                reason=f"project-workspace:{key}",
                board=board,
                title=f"Workspace visible: {board.name}",
                description=f"Mission Control is tracking the {board.name} project workspace.",
                status="in_progress" if key == "project-openclaw-mission-control" else "inbox",
            )

        await session.commit()

        counts = {
            "board_groups": (
                await session.exec(select(func.count()).select_from(BoardGroup))
            ).one(),
            "boards": (await session.exec(select(func.count()).select_from(Board))).one(),
            "tasks": (await session.exec(select(func.count()).select_from(Task))).one(),
            "agents": (await session.exec(select(func.count()).select_from(Agent))).one(),
            "runtime_agents": len(runtime_rows),
            "crons": len(crons.crons),
        }
        print(counts)


if __name__ == "__main__":
    asyncio.run(run())

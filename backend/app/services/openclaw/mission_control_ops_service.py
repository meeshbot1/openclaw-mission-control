"""Filesystem-backed OMX team scan service for Mission Control operations views."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from app.core.time import utcnow
from app.models.gateways import Gateway
from app.schemas.gateway_api import GatewayResolveQuery, GatewayRuntimeOverviewResponse
from app.schemas.mission_control import (
    MissionControlEventSummary,
    MissionControlGatewayRuntime,
    MissionControlMailboxMessage,
    MissionControlOperationsResponse,
    MissionControlTaskCounts,
    MissionControlTaskSummary,
    MissionControlTeamOperation,
    MissionControlWorkerStatus,
)
from app.services.openclaw.session_service import GatewaySessionService

PROJECT_WORKSPACE_ROOTS_ENV = "MISSION_CONTROL_PROJECT_WORKSPACE_ROOTS"
IGNORED_SCAN_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
}
MAX_SCAN_DEPTH = 5
MAX_RECENT_MESSAGES = 8
MAX_RECENT_EVENTS = 8


class MissionControlOperationsService:
    """Scan local OMX state roots and gateway runtimes for dashboard consumption."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def get_live_operations(
        self,
        *,
        organization_id: UUID,
    ) -> MissionControlOperationsResponse:
        gateways = await Gateway.objects.filter_by(organization_id=organization_id).all(
            self.session
        )
        scan_roots = self._scan_roots(gateways)
        teams = self._collect_team_operations(scan_roots)
        gateway_runtimes = await self._gateway_runtimes(
            gateways=gateways,
            organization_id=organization_id,
        )

        active_workers = sum(
            1 for team in teams for worker in team.workers if (worker.state or "").strip() == "busy"
        )
        summary = {
            "teams_total": len(teams),
            "tasks_total": sum(team.tasks_total for team in teams),
            "workers_total": sum(team.workers_total for team in teams),
            "workers_active": active_workers,
            "gateways_total": len(gateway_runtimes),
            "gateways_ok": sum(1 for runtime in gateway_runtimes if runtime.ok),
        }

        return MissionControlOperationsResponse(
            generated_at=utcnow().isoformat(),
            scanned_roots=[str(path) for path in scan_roots],
            summary=summary,
            teams=teams,
            gateways=gateway_runtimes,
        )

    def _scan_roots(self, gateways: list[Gateway]) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()

        def add(raw_path: str | None) -> None:
            if not raw_path:
                return
            normalized = Path(raw_path).expanduser()
            key = str(normalized)
            if key in seen:
                return
            seen.add(key)
            roots.append(normalized)

        for gateway in gateways:
            add((gateway.workspace_root or "").strip() or None)

        raw_configured_roots = os.environ.get(PROJECT_WORKSPACE_ROOTS_ENV, "").strip()
        if raw_configured_roots:
            for part in raw_configured_roots.replace("\n", ",").split(","):
                add(part.strip() or None)

        return roots

    def _collect_team_operations(self, scan_roots: list[Path]) -> list[MissionControlTeamOperation]:
        discovered: dict[tuple[str, str], MissionControlTeamOperation] = {}

        for scan_root in scan_roots:
            for state_root, project_root in self._discover_state_roots(scan_root):
                for team_dir in sorted((state_root / "team").iterdir(), key=lambda path: path.name):
                    if not team_dir.is_dir():
                        continue
                    team = self._load_team_operation(
                        team_dir=team_dir,
                        state_root=state_root,
                        project_root=project_root,
                    )
                    key = (team.team_name, team.state_root)
                    if key not in discovered:
                        discovered[key] = team

        return sorted(discovered.values(), key=lambda item: (item.team_name, item.state_root))

    def _discover_state_roots(self, scan_root: Path) -> list[tuple[Path, Path]]:
        if not scan_root.exists() or not scan_root.is_dir():
            return []

        found: dict[str, tuple[Path, Path]] = {}

        def maybe_add(project_root: Path) -> None:
            state_root = project_root / ".omx" / "state"
            if (state_root / "team").is_dir():
                found[str(state_root)] = (state_root, project_root)

        maybe_add(scan_root)
        for current_root, dirnames, _filenames in os.walk(scan_root):
            current_path = Path(current_root)
            try:
                depth = len(current_path.relative_to(scan_root).parts)
            except ValueError:
                depth = 0
            if depth > MAX_SCAN_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in IGNORED_SCAN_DIRS]
            if ".omx" in dirnames:
                maybe_add(current_path)
                dirnames.remove(".omx")

        return list(found.values())

    def _load_team_operation(
        self,
        *,
        team_dir: Path,
        state_root: Path,
        project_root: Path,
    ) -> MissionControlTeamOperation:
        config = self._read_json(team_dir / "config.json")
        tasks = self._task_summaries(team_dir / "tasks")
        monitor = self._read_json(team_dir / "monitor-snapshot.json")
        workers = self._worker_summaries(team_dir / "workers", monitor)
        messages = self._recent_messages(team_dir / "mailbox")
        events = self._recent_events(team_dir / "events" / "events.ndjson")
        counts = self._task_counts(tasks)

        configured_project_root = None
        if isinstance(config, dict):
            raw_leader_cwd = config.get("leader_cwd")
            if isinstance(raw_leader_cwd, str) and raw_leader_cwd.strip():
                configured_project_root = raw_leader_cwd.strip()

        return MissionControlTeamOperation(
            team_name=team_dir.name,
            task=(
                config.get("task")
                if isinstance(config, dict) and isinstance(config.get("task"), str)
                else None
            ),
            state_root=str(state_root),
            project_root=configured_project_root or str(project_root),
            tasks_total=len(tasks),
            workers_total=len(workers),
            task_counts=counts,
            tasks=tasks,
            workers=workers,
            recent_messages=messages,
            recent_events=events,
        )

    def _task_summaries(self, tasks_dir: Path) -> list[MissionControlTaskSummary]:
        items: list[MissionControlTaskSummary] = []
        if not tasks_dir.is_dir():
            return items
        for task_path in sorted(tasks_dir.glob("task-*.json"), key=lambda path: path.name):
            payload = self._read_json(task_path)
            if not isinstance(payload, dict):
                continue
            task_id = str(payload.get("id") or task_path.stem.removeprefix("task-"))
            subject = payload.get("subject")
            status = payload.get("status")
            owner = payload.get("owner")
            role = payload.get("role")
            items.append(
                MissionControlTaskSummary(
                    task_id=task_id,
                    subject=subject if isinstance(subject, str) else task_id,
                    status=status if isinstance(status, str) else "unknown",
                    owner=owner if isinstance(owner, str) else None,
                    role=role if isinstance(role, str) else None,
                )
            )
        return items

    def _task_counts(self, tasks: list[MissionControlTaskSummary]) -> MissionControlTaskCounts:
        counts = Counter((task.status or "unknown").strip() for task in tasks)
        return MissionControlTaskCounts(
            pending=counts.get("pending", 0),
            in_progress=counts.get("in_progress", 0),
            completed=counts.get("completed", 0),
            failed=counts.get("failed", 0),
            blocked=counts.get("blocked", 0),
            other=sum(
                count
                for status, count in counts.items()
                if status not in {"pending", "in_progress", "completed", "failed", "blocked"}
            ),
        )

    def _worker_summaries(
        self,
        workers_dir: Path,
        monitor_payload: Any,
    ) -> list[MissionControlWorkerStatus]:
        items: list[MissionControlWorkerStatus] = []
        state_by_name: dict[str, Any] = {}
        task_id_by_name: dict[str, Any] = {}
        alive_by_name: dict[str, Any] = {}
        if isinstance(monitor_payload, dict):
            state_by_name = monitor_payload.get("workerStateByName", {}) or {}
            task_id_by_name = monitor_payload.get("workerTaskIdByName", {}) or {}
            alive_by_name = monitor_payload.get("workerAliveByName", {}) or {}
        if not workers_dir.is_dir():
            return items
        for worker_dir in sorted(workers_dir.iterdir(), key=lambda path: path.name):
            if not worker_dir.is_dir():
                continue
            identity = self._read_json(worker_dir / "identity.json")
            status = self._read_json(worker_dir / "status.json")
            if not isinstance(identity, dict):
                continue
            name = identity.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            items.append(
                MissionControlWorkerStatus(
                    name=name,
                    role=identity.get("role") if isinstance(identity.get("role"), str) else None,
                    pane_id=(
                        identity.get("pane_id")
                        if isinstance(identity.get("pane_id"), str)
                        else None
                    ),
                    state=self._worker_state(name=name, status=status, state_by_name=state_by_name),
                    reason=(
                        status.get("reason")
                        if isinstance(status, dict) and isinstance(status.get("reason"), str)
                        else None
                    ),
                    task_id=(
                        str(task_id_by_name.get(name)).strip()
                        if task_id_by_name.get(name) not in {None, ""}
                        else None
                    ),
                    alive=bool(alive_by_name.get(name)) if name in alive_by_name else None,
                    updated_at=(
                        status.get("updated_at")
                        if isinstance(status, dict) and isinstance(status.get("updated_at"), str)
                        else None
                    ),
                )
            )
        return items

    @staticmethod
    def _worker_state(
        *,
        name: str,
        status: Any,
        state_by_name: dict[str, Any],
    ) -> str | None:
        if isinstance(status, dict):
            state = status.get("state")
            if isinstance(state, str) and state.strip():
                return state.strip()
        raw_state = state_by_name.get(name)
        if isinstance(raw_state, str) and raw_state.strip():
            return raw_state.strip()
        return None

    def _recent_messages(self, mailbox_dir: Path) -> list[MissionControlMailboxMessage]:
        items: list[MissionControlMailboxMessage] = []
        if not mailbox_dir.is_dir():
            return items
        for mailbox_path in sorted(mailbox_dir.glob("*.json"), key=lambda path: path.name):
            payload = self._read_json(mailbox_path)
            if not isinstance(payload, dict):
                continue
            messages = payload.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict):
                    continue
                body = message.get("body")
                items.append(
                    MissionControlMailboxMessage(
                        message_id=(
                            message.get("message_id")
                            if isinstance(message.get("message_id"), str)
                            else None
                        ),
                        from_worker=(
                            message.get("from_worker")
                            if isinstance(message.get("from_worker"), str)
                            else None
                        ),
                        to_worker=(
                            message.get("to_worker")
                            if isinstance(message.get("to_worker"), str)
                            else None
                        ),
                        body=body if isinstance(body, str) else "",
                        created_at=(
                            message.get("created_at")
                            if isinstance(message.get("created_at"), str)
                            else None
                        ),
                        delivered_at=(
                            message.get("delivered_at")
                            if isinstance(message.get("delivered_at"), str)
                            else None
                        ),
                    )
                )
        items.sort(key=lambda item: item.created_at or "", reverse=True)
        return items[:MAX_RECENT_MESSAGES]

    def _recent_events(self, events_path: Path) -> list[MissionControlEventSummary]:
        items: list[MissionControlEventSummary] = []
        if not events_path.is_file():
            return items
        for raw_line in events_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event_type = payload.get("type")
            if not isinstance(event_type, str) or not event_type.strip():
                continue
            items.append(
                MissionControlEventSummary(
                    event_id=(
                        payload.get("event_id")
                        if isinstance(payload.get("event_id"), str)
                        else None
                    ),
                    type=event_type,
                    worker=(
                        payload.get("worker") if isinstance(payload.get("worker"), str) else None
                    ),
                    message_id=(
                        payload.get("message_id")
                        if isinstance(payload.get("message_id"), str)
                        else None
                    ),
                    task_id=(
                        payload.get("task_id") if isinstance(payload.get("task_id"), str) else None
                    ),
                    created_at=(
                        payload.get("created_at")
                        if isinstance(payload.get("created_at"), str)
                        else None
                    ),
                )
            )
        items.sort(key=lambda item: item.created_at or "", reverse=True)
        return items[:MAX_RECENT_EVENTS]

    async def _gateway_runtimes(
        self,
        *,
        gateways: list[Gateway],
        organization_id: UUID,
    ) -> list[MissionControlGatewayRuntime]:
        service = GatewaySessionService(self.session)
        items: list[MissionControlGatewayRuntime] = []
        ordered_gateways = sorted(
            gateways, key=lambda gateway: (gateway.name or "", str(gateway.id))
        )
        for gateway in ordered_gateways:
            gateway_url = (gateway.url or "").strip() or None
            workspace_root = (gateway.workspace_root or "").strip() or None
            if gateway_url is None:
                items.append(
                    MissionControlGatewayRuntime(
                        gateway_id=gateway.id,
                        gateway_name=gateway.name,
                        gateway_url=None,
                        workspace_root=workspace_root,
                        ok=False,
                        error="Gateway url is required",
                    )
                )
                continue
            params = GatewayResolveQuery(
                gateway_url=gateway_url,
                gateway_token=(gateway.token or "").strip() or None,
                gateway_allow_insecure_tls=gateway.allow_insecure_tls,
                gateway_disable_device_pairing=gateway.disable_device_pairing,
            )
            try:
                overview = await service.get_runtime_overview(
                    params=params,
                    organization_id=organization_id,
                    user=None,
                )
                items.append(self._runtime_from_overview(gateway, workspace_root, overview))
            except HTTPException as exc:
                items.append(
                    MissionControlGatewayRuntime(
                        gateway_id=gateway.id,
                        gateway_name=gateway.name,
                        gateway_url=gateway_url,
                        workspace_root=workspace_root,
                        ok=False,
                        error=self._http_error_detail(exc),
                    )
                )
        return items

    @staticmethod
    def _runtime_from_overview(
        gateway: Gateway,
        workspace_root: str | None,
        overview: GatewayRuntimeOverviewResponse,
    ) -> MissionControlGatewayRuntime:
        return MissionControlGatewayRuntime(
            gateway_id=gateway.id,
            gateway_name=gateway.name,
            gateway_url=(gateway.url or "").strip() or None,
            workspace_root=workspace_root,
            ok=True,
            generated_at_ms=overview.generated_at_ms,
            summary=overview.summary,
            agents=overview.agents,
            subagents=overview.subagents,
        )

    @staticmethod
    def _http_error_detail(exc: HTTPException) -> str:
        if isinstance(exc.detail, str):
            return exc.detail
        try:
            return json.dumps(exc.detail)
        except TypeError:
            return str(exc.detail)

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

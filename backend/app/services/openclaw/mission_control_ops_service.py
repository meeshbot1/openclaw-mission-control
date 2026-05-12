"""Filesystem-backed OMX team scan service for Mission Control operations views."""

from __future__ import annotations

import asyncio
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
    MissionControlCodexEvent,
    MissionControlCodexSession,
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
ACTIVE_WORKER_STATES = {"busy", "working", "in_progress"}
MAX_CODEX_SESSIONS = 50
MAX_CODEX_EVENTS = 8
GATEWAY_RUNTIME_TIMEOUT_SECONDS = 3.0
CODEX_EVENT_TYPES = {
    "model.completed": "message",
    "prompt.submitted": "command",
    "session.ended": "status",
    "session.started": "status",
    "tool.call": "tool",
    "tool.result": "tool",
    "tool.started": "tool",
    "tool.completed": "tool",
    "reasoning.delta": "thinking",
    "reasoning.summary": "thinking",
}


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
        codex_sessions = self._collect_codex_sessions(scan_roots)
        gateway_runtimes = await self._gateway_runtimes(
            gateways=gateways,
            organization_id=organization_id,
        )

        active_workers = sum(
            1
            for team in teams
            for worker in team.workers
            if (worker.state or "").strip().lower() in ACTIVE_WORKER_STATES
        )
        summary = {
            "teams_total": len(teams),
            "tasks_total": sum(team.tasks_total for team in teams),
            "workers_total": sum(team.workers_total for team in teams),
            "workers_active": active_workers,
            "gateways_total": len(gateway_runtimes),
            "gateways_ok": sum(1 for runtime in gateway_runtimes if runtime.ok),
            "codex_sessions_total": len(codex_sessions),
            "codex_sessions_active": sum(1 for session in codex_sessions if session.active),
        }

        return MissionControlOperationsResponse(
            generated_at=utcnow().isoformat(),
            scanned_roots=[str(path) for path in scan_roots],
            summary=summary,
            teams=teams,
            gateways=gateway_runtimes,
            codex_sessions=codex_sessions,
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

    def _collect_codex_sessions(self, scan_roots: list[Path]) -> list[MissionControlCodexSession]:
        discovered: dict[str, MissionControlCodexSession] = {}

        for binding_path in self._discover_codex_binding_paths(scan_roots):
            binding = self._read_json(binding_path)
            if not isinstance(binding, dict):
                continue
            thread_id = binding.get("threadId")
            session_file = binding.get("sessionFile")
            if not isinstance(thread_id, str) or not thread_id.strip():
                continue
            if not isinstance(session_file, str) or not session_file.strip():
                continue
            session_path = Path(session_file)
            events = self._codex_events_for_session(session_path)
            discovered[thread_id] = MissionControlCodexSession(
                thread_id=thread_id,
                agent_id=self._agent_id_from_session_file(session_path),
                session_file=session_file,
                session_key=self._session_key_for_session(session_path),
                cwd=binding.get("cwd") if isinstance(binding.get("cwd"), str) else None,
                model=binding.get("model") if isinstance(binding.get("model"), str) else None,
                model_provider=(
                    binding.get("modelProvider")
                    if isinstance(binding.get("modelProvider"), str)
                    else None
                ),
                auth_profile_id=(
                    binding.get("authProfileId")
                    if isinstance(binding.get("authProfileId"), str)
                    else None
                ),
                active=self._codex_session_active(events),
                updated_at=(
                    binding.get("updatedAt")
                    if isinstance(binding.get("updatedAt"), str)
                    else None
                ),
                recent_events=events,
            )

        return sorted(
            discovered.values(),
            key=self._codex_session_sort_key,
            reverse=True,
        )[:MAX_CODEX_SESSIONS]

    def _discover_codex_binding_paths(self, scan_roots: list[Path]) -> list[Path]:
        paths: dict[str, Path] = {}
        for scan_root in scan_roots:
            for root in self._codex_scan_candidates(scan_root):
                if not root.exists() or not root.is_dir():
                    continue
                for current_root, dirnames, filenames in os.walk(root):
                    current_path = Path(current_root)
                    try:
                        depth = len(current_path.relative_to(root).parts)
                    except ValueError:
                        depth = 0
                    if depth > MAX_SCAN_DEPTH:
                        dirnames[:] = []
                        continue
                    dirnames[:] = [name for name in dirnames if name not in IGNORED_SCAN_DIRS]
                    for filename in filenames:
                        if filename.endswith(".codex-app-server.json"):
                            path = current_path / filename
                            paths[str(path)] = path
        return sorted(paths.values(), key=lambda path: str(path))

    def _codex_scan_candidates(self, scan_root: Path) -> list[Path]:
        candidates = [scan_root]
        if scan_root.name == "projects" and scan_root.parent.name == "workspace":
            openclaw_root = scan_root.parent.parent
            candidates.append(openclaw_root / "agents")
        agents_root = scan_root / "agents"
        if agents_root.is_dir():
            candidates.insert(0, agents_root)
        return list(dict.fromkeys(candidates))

    def _codex_events_for_session(self, session_path: Path) -> list[MissionControlCodexEvent]:
        for trajectory_path in self._trajectory_path_candidates(session_path):
            events = self._codex_events_from_trajectory(trajectory_path)
            if events:
                return events[:MAX_CODEX_EVENTS]
        return self._codex_events_from_transcript(session_path)[:MAX_CODEX_EVENTS]

    @staticmethod
    def _trajectory_path_candidates(session_path: Path) -> list[Path]:
        legacy_path = session_path.with_suffix(session_path.suffix + ".trajectory.jsonl")
        current_path = session_path.with_suffix(".trajectory.jsonl")
        return list(dict.fromkeys([legacy_path, current_path]))

    def _codex_events_from_trajectory(self, path: Path) -> list[MissionControlCodexEvent]:
        items: list[MissionControlCodexEvent] = []
        for payload in self._read_json_lines(path):
            raw_type = payload.get("type")
            if not isinstance(raw_type, str):
                continue
            raw_data = payload.get("data")
            data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
            event_type = CODEX_EVENT_TYPES.get(raw_type, raw_type)
            summary = self._codex_event_summary(raw_type, data)
            if not summary:
                continue
            items.append(
                MissionControlCodexEvent(
                    type=event_type,
                    summary=summary,
                    created_at=payload.get("ts") if isinstance(payload.get("ts"), str) else None,
                    run_id=payload.get("runId") if isinstance(payload.get("runId"), str) else None,
                    turn_id=data.get("turnId") if isinstance(data.get("turnId"), str) else None,
                )
            )
        items.sort(key=lambda item: item.created_at or "", reverse=True)
        return items

    def _codex_events_from_transcript(self, path: Path) -> list[MissionControlCodexEvent]:
        items: list[MissionControlCodexEvent] = []
        for payload in self._read_json_lines(path):
            message = payload.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            summary = self._message_summary(content)
            if not isinstance(role, str) or not summary:
                continue
            items.append(
                MissionControlCodexEvent(
                    type="message",
                    summary=f"{role}: {summary}",
                    created_at=payload.get("timestamp")
                    if isinstance(payload.get("timestamp"), str)
                    else None,
                )
            )
        items.sort(key=lambda item: item.created_at or "", reverse=True)
        return items

    def _codex_event_summary(self, raw_type: str, data: dict[str, Any]) -> str | None:
        if raw_type == "prompt.submitted":
            prompt = data.get("prompt")
            return f"User prompt: {self._truncate(prompt)}" if isinstance(prompt, str) else None
        if raw_type == "model.completed":
            texts = data.get("assistantTexts")
            if isinstance(texts, list) and texts:
                first = next((item for item in texts if isinstance(item, str) and item.strip()), None)
                if first:
                    return f"Assistant reply: {self._truncate(first)}"
            usage = data.get("usage")
            return f"Model completed ({usage})" if usage else "Model completed"
        if raw_type == "session.started":
            tool_count = data.get("toolCount")
            return f"Session started ({tool_count} tools)" if tool_count is not None else "Session started"
        if raw_type == "session.ended":
            status = data.get("status")
            return f"Session ended: {status}" if isinstance(status, str) else "Session ended"
        return self._truncate(data.get("summary") or data.get("message") or raw_type)

    @staticmethod
    def _message_summary(content: Any) -> str | None:
        if isinstance(content, str):
            return MissionControlOperationsService._truncate(content)
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            if texts:
                return MissionControlOperationsService._truncate(" ".join(texts))
        return None

    @staticmethod
    def _truncate(value: Any, max_length: int = 220) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            return None
        return f"{cleaned[: max_length - 1]}…" if len(cleaned) > max_length else cleaned

    @staticmethod
    def _agent_id_from_session_file(session_path: Path) -> str | None:
        parts = session_path.parts
        if "agents" not in parts:
            return None
        index = parts.index("agents")
        if index + 1 >= len(parts):
            return None
        return parts[index + 1]

    def _session_key_for_session(self, session_path: Path) -> str | None:
        for path in self._trajectory_path_candidates(session_path):
            for payload in self._read_json_lines(path):
                session_key = payload.get("sessionKey")
                if isinstance(session_key, str) and session_key.strip():
                    return session_key.strip()
        return None

    @staticmethod
    def _codex_session_sort_key(item: MissionControlCodexSession) -> str:
        if item.updated_at:
            return item.updated_at
        if item.recent_events:
            return item.recent_events[0].created_at or ""
        return ""

    @staticmethod
    def _codex_session_active(events: list[MissionControlCodexEvent]) -> bool:
        if not events:
            return False
        latest = events[0]
        return latest.type != "status" or "ended" not in latest.summary.lower()

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
        workers = self._worker_summaries(team_dir / "workers", monitor, tasks)
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
        tasks: list[MissionControlTaskSummary],
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
            task_id = self._worker_task_id(name=name, tasks=tasks, task_id_by_name=task_id_by_name)
            items.append(
                MissionControlWorkerStatus(
                    name=name,
                    role=identity.get("role") if isinstance(identity.get("role"), str) else None,
                    pane_id=(
                        identity.get("pane_id")
                        if isinstance(identity.get("pane_id"), str)
                        else None
                    ),
                    state=self._worker_state(
                        name=name,
                        status=status,
                        state_by_name=state_by_name,
                        alive_by_name=alive_by_name,
                        task_id=task_id,
                    ),
                    reason=(
                        status.get("reason")
                        if isinstance(status, dict) and isinstance(status.get("reason"), str)
                        else None
                    ),
                    task_id=task_id,
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
        alive_by_name: dict[str, Any],
        task_id: str | None,
    ) -> str | None:
        if isinstance(status, dict):
            state = status.get("state")
            if isinstance(state, str) and state.strip():
                return state.strip()
        raw_state = state_by_name.get(name)
        if isinstance(raw_state, str) and raw_state.strip() and raw_state.strip().lower() != "unknown":
            return raw_state.strip()
        if bool(alive_by_name.get(name)) and task_id:
            return "in_progress"
        return None

    @staticmethod
    def _worker_task_id(
        *,
        name: str,
        tasks: list[MissionControlTaskSummary],
        task_id_by_name: dict[str, Any],
    ) -> str | None:
        raw_task_id = task_id_by_name.get(name)
        if raw_task_id not in {None, ""}:
            return str(raw_task_id).strip()
        for task in tasks:
            if task.owner == name and (task.status or "").strip().lower() == "in_progress":
                return task.task_id
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
                gateway_token=(
                    None
                    if service._env_gateway_token_for_url(gateway_url)
                    else (gateway.token or "").strip() or None
                ),
                gateway_allow_insecure_tls=gateway.allow_insecure_tls,
                gateway_disable_device_pairing=gateway.disable_device_pairing,
            )
            try:
                overview = await asyncio.wait_for(
                    service.get_runtime_overview(
                        params=params,
                        organization_id=organization_id,
                        user=None,
                    ),
                    timeout=GATEWAY_RUNTIME_TIMEOUT_SECONDS,
                )
                items.append(self._runtime_from_overview(gateway, workspace_root, overview))
            except TimeoutError:
                items.append(
                    MissionControlGatewayRuntime(
                        gateway_id=gateway.id,
                        gateway_name=gateway.name,
                        gateway_url=gateway_url,
                        workspace_root=workspace_root,
                        ok=False,
                        error=(
                            "Gateway runtime overview timed out after "
                            f"{GATEWAY_RUNTIME_TIMEOUT_SECONDS:g}s"
                        ),
                    )
                )
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

    def _read_json_lines(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        items: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items

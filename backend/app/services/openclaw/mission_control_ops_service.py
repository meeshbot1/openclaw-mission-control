"""Filesystem-backed OMX team scan service for Mission Control operations views."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
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
    MissionControlErrorRegistryItem,
    MissionControlErrorRegistryResponse,
    MissionControlErrorRegistrySummary,
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
ERROR_REGISTRY_DB_ENV = "OPENCLAW_ERROR_DB"
DEFAULT_ERROR_REGISTRY_DB = Path("/home/amish/.openclaw/logs/openclaw-error-registry.db")
LEGACY_ERROR_REGISTRY_DB = Path("/home/amish/.openclaw/workspace/ops/gateway_ops.db")
CRON_JOBS_PATH = Path("/home/amish/.openclaw/cron/jobs.json")
CRON_JOBS_STATE_PATH = Path("/home/amish/.openclaw/cron/jobs-state.json")
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
MAX_ERROR_REGISTRY_ITEMS = 500
ERROR_REGISTRY_DEFAULT_LIMIT = 200
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

    def get_error_registry(
        self,
        *,
        status: str | None = "open",
        limit: int = ERROR_REGISTRY_DEFAULT_LIMIT,
    ) -> MissionControlErrorRegistryResponse:
        """Return a read-only operator view over the local OpenClaw error registry."""

        db_path = self._error_registry_db_path()
        generated_at = utcnow().isoformat()
        if db_path is None:
            return MissionControlErrorRegistryResponse(
                db_path=None,
                generated_at=generated_at,
            )

        limit = max(1, min(limit, MAX_ERROR_REGISTRY_ITEMS))
        cron_jobs = self._load_cron_jobs()
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            columns = self._sqlite_columns(conn, "error_events")
            if not columns:
                return MissionControlErrorRegistryResponse(
                    db_path=str(db_path),
                    generated_at=generated_at,
                )
            rows = self._error_registry_rows(
                conn=conn,
                columns=columns,
                status=status,
                limit=limit,
            )

        items = [
            self._error_registry_item(row, columns=columns, cron_jobs=cron_jobs) for row in rows
        ]
        summary_counts = Counter(item.status for item in items)
        return MissionControlErrorRegistryResponse(
            db_path=str(db_path),
            generated_at=generated_at,
            summary=MissionControlErrorRegistrySummary(
                total=len(items),
                open=summary_counts.get("open", 0),
                observed=summary_counts.get("observed", 0),
                ignored=summary_counts.get("ignored", 0),
                fixed=summary_counts.get("fixed", 0),
                assigned=sum(
                    1 for item in items if item.assigned_agent_id or item.assigned_cron_id
                ),
                working=sum(1 for item in items if item.assignment_state == "working"),
            ),
            items=items,
        )

    def _error_registry_db_path(self) -> Path | None:
        configured = os.environ.get(ERROR_REGISTRY_DB_ENV, "").strip()
        candidates = [
            Path(configured).expanduser() if configured else None,
            DEFAULT_ERROR_REGISTRY_DB,
            LEGACY_ERROR_REGISTRY_DB,
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _error_registry_rows(
        *,
        conn: sqlite3.Connection,
        columns: set[str],
        status: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        select_columns = [
            "id",
            "fingerprint",
            "source_kind",
            "source",
            "event_ts",
            "level",
            "message",
            "status",
            "fix_attempts",
            "last_seen_at",
            "last_fix_attempt_at",
            "fixed_at",
        ]
        for optional in ("service", "category", "fix_type", "metadata_json"):
            if optional in columns:
                select_columns.append(optional)
        where = ""
        params: list[Any] = []
        normalized_status = (status or "").strip().lower()
        if normalized_status and normalized_status != "all":
            where = "WHERE status = ?"
            params.append(normalized_status)
        params.append(limit)
        return conn.execute(
            f"""
            SELECT {", ".join(select_columns)}
            FROM error_events
            {where}
            ORDER BY event_ts DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _error_registry_item(
        self,
        row: sqlite3.Row,
        *,
        columns: set[str],
        cron_jobs: list[dict[str, Any]],
    ) -> MissionControlErrorRegistryItem:
        def value(key: str) -> Any:
            return row[key] if key in row.keys() else None

        source = str(value("source") or "")
        message = str(value("message") or "")
        service = self._string_or_none(value("service")) or self._infer_error_service(
            source=source,
            message=message,
        )
        category = self._string_or_none(value("category")) or self._infer_error_category(
            source=source,
            message=message,
            service=service,
        )
        fix_type = self._string_or_none(value("fix_type")) or self._infer_error_fix_type(
            category=category,
            source=source,
            message=message,
        )
        matched_cron = self._match_cron_job(source=source, message=message, cron_jobs=cron_jobs)
        assigned_agent_id = (
            self._string_or_none(matched_cron.get("agentId")) if matched_cron else None
        ) or self._assigned_agent_for_error(service=service, category=category, source=source)
        cron = matched_cron or self._infer_remediation_cron(
            assigned_agent_id=assigned_agent_id,
            service=service,
            category=category,
            fix_type=fix_type,
            cron_jobs=cron_jobs,
        )
        assignment_state = self._cron_assignment_state(cron)
        action_items = self._error_action_items(
            category=category,
            fix_type=fix_type,
            source=source,
            message=message,
            cron=cron,
        )

        return MissionControlErrorRegistryItem(
            id=int(value("id") or 0),
            fingerprint=self._string_or_none(value("fingerprint")),
            source_kind=str(value("source_kind") or "unknown"),
            source=source,
            event_ts=str(value("event_ts") or ""),
            level=str(value("level") or "error"),
            service=service,
            category=category,
            fix_type=fix_type,
            message=self._truncate(message, 500) or "",
            status=str(value("status") or "open"),
            fix_attempts=int(value("fix_attempts") or 0),
            last_seen_at=str(value("last_seen_at") or value("event_ts") or ""),
            last_fix_attempt_at=self._string_or_none(value("last_fix_attempt_at")),
            fixed_at=self._string_or_none(value("fixed_at")),
            assigned_agent_id=assigned_agent_id,
            assigned_cron_id=self._string_or_none(cron.get("id")) if cron else None,
            assigned_cron_name=self._string_or_none(cron.get("name")) if cron else None,
            assigned_cron_schedule=self._cron_schedule_label(cron),
            assigned_cron_timezone=self._cron_timezone(cron),
            assigned_cron_enabled=self._cron_enabled(cron),
            assigned_cron_next_run_at_ms=self._cron_int_state(cron, "nextRunAtMs"),
            assigned_cron_last_run_at_ms=self._cron_int_state(cron, "lastRunAtMs"),
            assigned_cron_last_run_status=self._cron_string_state(
                cron,
                "lastRunStatus",
                "lastStatus",
            ),
            remediation_schedule_status=self._cron_schedule_status(cron),
            assignment_state=assignment_state,
            assignment_reason=fix_type or category or service,
            action_items=action_items,
        )

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _load_cron_jobs() -> list[dict[str, Any]]:
        if not CRON_JOBS_PATH.is_file():
            return []
        try:
            payload = json.loads(CRON_JOBS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            return []
        states = MissionControlOperationsService._load_cron_job_states()
        merged_jobs: list[dict[str, Any]] = []
        for raw_job in jobs:
            if not isinstance(raw_job, dict):
                continue
            job = dict(raw_job)
            job_id = MissionControlOperationsService._string_or_none(job.get("id"))
            state = states.get(job_id or "")
            if state:
                existing_state = job.get("state")
                merged_state = dict(existing_state) if isinstance(existing_state, dict) else {}
                merged_state.update(state)
                job["state"] = merged_state
            merged_jobs.append(job)
        return merged_jobs

    @staticmethod
    def _load_cron_job_states() -> dict[str, dict[str, Any]]:
        if not CRON_JOBS_STATE_PATH.is_file():
            return {}
        try:
            payload = json.loads(CRON_JOBS_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, dict):
            return {}
        states: dict[str, dict[str, Any]] = {}
        for job_id, raw_state in jobs.items():
            if not isinstance(job_id, str) or not isinstance(raw_state, dict):
                continue
            state = raw_state.get("state")
            if isinstance(state, dict):
                states[job_id] = state
            else:
                states[job_id] = raw_state
        return states

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _match_cron_job(
        self,
        *,
        source: str,
        message: str,
        cron_jobs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        haystack = f"{source}\n{message}".lower()
        source_slug = self._slug(
            Path(source).name.removeprefix("openclaw-").removesuffix(".service")
        )
        for job in cron_jobs:
            job_id = self._string_or_none(job.get("id"))
            job_name = self._string_or_none(job.get("name"))
            candidates = [item for item in (job_id, job_name) if item]
            if any(candidate.lower() in haystack for candidate in candidates):
                return job
            if any(self._slug(candidate) == source_slug for candidate in candidates):
                return job
        return None

    def _infer_remediation_cron(
        self,
        *,
        assigned_agent_id: str,
        service: str | None,
        category: str | None,
        fix_type: str | None,
        cron_jobs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        preferred_slugs = self._preferred_remediation_cron_slugs(
            service=service,
            category=category,
            fix_type=fix_type,
        )
        if not preferred_slugs:
            return None
        for preferred_slug in preferred_slugs:
            for job in cron_jobs:
                job_agent_id = self._string_or_none(job.get("agentId"))
                if job_agent_id and job_agent_id != assigned_agent_id:
                    continue
                if self._cron_matches_slug(job, preferred_slug):
                    return job
            for job in cron_jobs:
                if self._cron_matches_slug(job, preferred_slug):
                    return job
        return None

    @staticmethod
    def _preferred_remediation_cron_slugs(
        *,
        service: str | None,
        category: str | None,
        fix_type: str | None,
    ) -> list[str]:
        if service == "mission-control" or category == "mission-control-health":
            return ["mission-control-stabilizer-nightly", "mission-control-stabilizer"]
        if fix_type == "gateway-token-repair":
            return [
                "gateway-health-check",
                "gateway-approved-fix-executor",
                "gateway-error-digest",
            ]
        if fix_type == "gateway-health-check" or category == "gateway-health":
            return ["gateway-health-check", "gateway-log-scan"]
        if fix_type == "restart-user-service" or category == "systemd-health":
            return ["openclaw-self-stabilizer", "gateway-maintenance-window"]
        if fix_type == "disk-cleanup-review" or category == "disk-health":
            return ["gateway-disk-usage-scan"]
        return []

    def _cron_matches_slug(self, cron: dict[str, Any], slug: str) -> bool:
        candidates = (
            self._string_or_none(cron.get("id")),
            self._string_or_none(cron.get("name")),
        )
        return any(candidate and slug in self._slug(candidate) for candidate in candidates)

    @staticmethod
    def _infer_error_service(*, source: str, message: str) -> str:
        low = f"{source}\n{message}".lower()
        for token in (
            "mission-control",
            "gateway",
            "cron",
            "telegram",
            "discord",
            "openai",
            "google",
            "qmd",
            "sqlite",
            "sandbox",
            "ollama",
        ):
            if token in low:
                return token
        return "openclaw"

    @staticmethod
    def _infer_error_category(*, source: str, message: str, service: str | None) -> str:
        low = f"{source}\n{message}".lower()
        if "gateway token mismatch" in low or "token_mismatch" in low:
            return "gateway-token-drift"
        if service == "mission-control" or "uvicorn app.main" in low or "next-server" in low:
            return "mission-control-health"
        if ".service" in low or ".timer" in low or "systemd" in low:
            return "systemd-health"
        if "disk" in low or "no space left" in low:
            return "disk-health"
        if "ollama" in low or "11434" in low or "11435" in low:
            return "optional-ollama"
        if service == "gateway":
            return "gateway-health"
        return "runtime-error"

    @staticmethod
    def _infer_error_fix_type(*, category: str | None, source: str, message: str) -> str | None:
        low = f"{source}\n{message}".lower()
        if category == "gateway-token-drift":
            return "gateway-token-repair"
        if category == "mission-control-health" or category == "systemd-health":
            return "restart-user-service"
        if category == "disk-health":
            return "disk-cleanup-review"
        if "health-check" in low or category == "gateway-health":
            return "gateway-health-check"
        return None

    @staticmethod
    def _assigned_agent_for_error(
        *,
        service: str | None,
        category: str | None,
        source: str,
    ) -> str:
        low = source.lower()
        if service == "mission-control" or category == "mission-control-health":
            return "dev-projects-mission-control"
        if "medical-team" in low:
            return "dev-projects-medical-team-platform-app"
        return "ops"

    def _cron_assignment_state(self, cron: dict[str, Any] | None) -> str:
        if not cron:
            return "assigned"
        status = (self._cron_string_state(cron, "lastRunStatus", "lastStatus") or "").lower()
        if self._cron_int_state(cron, "runningAtMs") is not None or status == "running":
            return "working"
        if self._cron_int_state(cron, "nextRunAtMs") is not None:
            return "queued"
        return "assigned"

    @staticmethod
    def _cron_state(cron: dict[str, Any] | None) -> dict[str, Any]:
        if not cron:
            return {}
        state = cron.get("state")
        return state if isinstance(state, dict) else {}

    def _cron_string_state(self, cron: dict[str, Any] | None, *keys: str) -> str | None:
        state = self._cron_state(cron)
        for key in keys:
            value = self._string_or_none(state.get(key))
            if value:
                return value
            value = self._string_or_none(cron.get(key)) if cron else None
            if value:
                return value
        return None

    @staticmethod
    def _cron_int_state(cron: dict[str, Any] | None, key: str) -> int | None:
        if not cron:
            return None
        state = MissionControlOperationsService._cron_state(cron)
        for source in (state, cron):
            value = source.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip():
                try:
                    return int(float(value))
                except ValueError:
                    continue
        return None

    @staticmethod
    def _cron_enabled(cron: dict[str, Any] | None) -> bool | None:
        if not cron:
            return None
        enabled = cron.get("enabled")
        return enabled if isinstance(enabled, bool) else None

    def _cron_schedule_label(self, cron: dict[str, Any] | None) -> str | None:
        if not cron:
            return None
        schedule = cron.get("schedule")
        if isinstance(schedule, str):
            return self._string_or_none(schedule)
        if isinstance(schedule, dict):
            kind = self._string_or_none(schedule.get("kind"))
            expr = self._string_or_none(schedule.get("expr"))
            every_ms = self._cron_int_state({"state": schedule}, "everyMs")
            if kind and expr:
                return f"{kind}: {expr}"
            if expr:
                return expr
            if kind == "every" and every_ms:
                return f"every {round(every_ms / 60000)} min"
        return self._string_or_none(cron.get("cron")) or self._string_or_none(
            cron.get("expression")
        )

    def _cron_timezone(self, cron: dict[str, Any] | None) -> str | None:
        if not cron:
            return None
        schedule = cron.get("schedule")
        if isinstance(schedule, dict):
            return self._string_or_none(schedule.get("tz"))
        return self._string_or_none(cron.get("tz"))

    def _cron_schedule_status(self, cron: dict[str, Any] | None) -> str:
        if not cron:
            return "not-scheduled"
        if self._cron_int_state(cron, "runningAtMs") is not None:
            return "running"
        if self._cron_enabled(cron) is False:
            return "disabled"
        if self._cron_int_state(cron, "nextRunAtMs") is not None:
            return "scheduled"
        if self._cron_schedule_label(cron):
            return "schedule-pending"
        return "not-scheduled"

    def _error_action_items(
        self,
        *,
        category: str | None,
        fix_type: str | None,
        source: str,
        message: str,
        cron: dict[str, Any] | None,
    ) -> list[str]:
        low = f"{source}\n{message}".lower()
        items: list[str] = []
        if cron:
            name = self._string_or_none(cron.get("name")) or self._string_or_none(cron.get("id"))
            if name:
                items.append(
                    f"Review the `{name}` cron's last run output and rerun after fixing the cause."
                )
                if self._cron_enabled(cron) is False:
                    items.append(
                        f"`{name}` is disabled; enable it or run it manually before expecting an automatic fix."
                    )
                elif self._cron_int_state(cron, "nextRunAtMs") is None:
                    items.append(f"Verify the scheduler has calculated the next run for `{name}`.")
        if fix_type == "gateway-token-repair":
            items.extend(
                [
                    "Verify `gateway.remote.token` matches `gateway.auth.token`.",
                    "Restart the gateway after token repair and confirm `/api/v1/gateways/status` is healthy.",
                ]
            )
        elif fix_type == "restart-user-service":
            items.append(
                "Inspect the service journal, restart the affected user service, and re-check health."
            )
        elif fix_type == "gateway-health-check":
            items.append(
                "Run the gateway health check and inspect gateway logs for the same fingerprint."
            )
        elif fix_type == "disk-cleanup-review":
            items.append(
                "Review disk usage and clean generated logs or artifacts before retrying failed work."
            )
        elif category == "optional-ollama":
            items.append(
                "Confirm whether Ollama is required; otherwise keep optional Ollama noise ignored."
            )
        elif "lsof failed" in low:
            items.append(
                "Install or restore `lsof`, or suppress the stale-pid scan warning if startup is healthy."
            )
        else:
            items.append(
                "Review the source log, assign remediation owner, and mark the error fixed after verification."
            )
        return list(dict.fromkeys(items))[:5]

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
                    binding.get("updatedAt") if isinstance(binding.get("updatedAt"), str) else None
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
                    created_at=(
                        payload.get("timestamp")
                        if isinstance(payload.get("timestamp"), str)
                        else None
                    ),
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
                first = next(
                    (item for item in texts if isinstance(item, str) and item.strip()), None
                )
                if first:
                    return f"Assistant reply: {self._truncate(first)}"
            usage = data.get("usage")
            return f"Model completed ({usage})" if usage else "Model completed"
        if raw_type == "session.started":
            tool_count = data.get("toolCount")
            return (
                f"Session started ({tool_count} tools)"
                if tool_count is not None
                else "Session started"
            )
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
        if (
            isinstance(raw_state, str)
            and raw_state.strip()
            and raw_state.strip().lower() != "unknown"
        ):
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

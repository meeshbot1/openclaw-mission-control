"""Schemas for Mission Control live operations dashboard responses."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Field, SQLModel

from app.schemas.gateway_api import GatewayRuntimeSessionStatus


class MissionControlTaskCounts(SQLModel):
    """Aggregated task-status counts for one team."""

    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    other: int = 0


class MissionControlTaskSummary(SQLModel):
    """Compact task row for dashboard listing."""

    task_id: str
    subject: str
    status: str
    owner: str | None = None
    role: str | None = None


class MissionControlWorkerStatus(SQLModel):
    """Normalized worker pane status for one OMX team worker."""

    name: str
    role: str | None = None
    pane_id: str | None = None
    state: str | None = None
    reason: str | None = None
    task_id: str | None = None
    alive: bool | None = None
    updated_at: str | None = None


class MissionControlMailboxMessage(SQLModel):
    """Recent mailbox message exposed on the operations dashboard."""

    message_id: str | None = None
    from_worker: str | None = None
    to_worker: str | None = None
    body: str
    created_at: str | None = None
    delivered_at: str | None = None


class MissionControlEventSummary(SQLModel):
    """Recent team event line exposed on the operations dashboard."""

    event_id: str | None = None
    type: str
    worker: str | None = None
    message_id: str | None = None
    task_id: str | None = None
    created_at: str | None = None


class MissionControlCodexEvent(SQLModel):
    """Recent Codex/OpenClaw runtime event for a Codex-backed session."""

    type: str
    summary: str
    created_at: str | None = None
    run_id: str | None = None
    turn_id: str | None = None


class MissionControlCodexSession(SQLModel):
    """Codex app-server session attachment discovered from OpenClaw session state."""

    thread_id: str
    agent_id: str | None = None
    session_file: str
    session_key: str | None = None
    cwd: str | None = None
    model: str | None = None
    model_provider: str | None = None
    auth_profile_id: str | None = None
    active: bool = False
    updated_at: str | None = None
    recent_events: list[MissionControlCodexEvent] = Field(default_factory=list)


class MissionControlTeamOperation(SQLModel):
    """Normalized live team-operation snapshot for one discovered OMX team."""

    team_name: str
    task: str | None = None
    state_root: str
    project_root: str | None = None
    tasks_total: int = 0
    workers_total: int = 0
    task_counts: MissionControlTaskCounts = Field(default_factory=MissionControlTaskCounts)
    tasks: list[MissionControlTaskSummary] = Field(default_factory=list)
    workers: list[MissionControlWorkerStatus] = Field(default_factory=list)
    recent_messages: list[MissionControlMailboxMessage] = Field(default_factory=list)
    recent_events: list[MissionControlEventSummary] = Field(default_factory=list)


class MissionControlGatewayRuntime(SQLModel):
    """Gateway runtime snapshot included alongside discovered OMX team data."""

    gateway_id: UUID
    gateway_name: str
    gateway_url: str | None = None
    workspace_root: str | None = None
    ok: bool
    error: str | None = None
    generated_at_ms: int | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    agents: list[GatewayRuntimeSessionStatus] = Field(default_factory=list)
    subagents: list[GatewayRuntimeSessionStatus] = Field(default_factory=list)


class MissionControlOperationsResponse(SQLModel):
    """Aggregated live-operations response for the Mission Control dashboard."""

    generated_at: str
    scanned_roots: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    teams: list[MissionControlTeamOperation] = Field(default_factory=list)
    gateways: list[MissionControlGatewayRuntime] = Field(default_factory=list)
    codex_sessions: list[MissionControlCodexSession] = Field(default_factory=list)


class MissionControlErrorRegistryItem(SQLModel):
    """Read-only row from the local OpenClaw error registry."""

    id: int
    fingerprint: str | None = None
    source_kind: str
    source: str
    event_ts: str
    level: str
    service: str | None = None
    category: str | None = None
    fix_type: str | None = None
    message: str
    status: str
    fix_attempts: int = 0
    last_seen_at: str
    last_fix_attempt_at: str | None = None
    fixed_at: str | None = None
    assigned_agent_id: str | None = None
    assigned_cron_id: str | None = None
    assigned_cron_name: str | None = None
    assigned_cron_schedule: str | None = None
    assigned_cron_timezone: str | None = None
    assigned_cron_enabled: bool | None = None
    assigned_cron_next_run_at_ms: int | None = None
    assigned_cron_last_run_at_ms: int | None = None
    assigned_cron_last_run_status: str | None = None
    remediation_schedule_status: str = "not-scheduled"
    assignment_state: str = "assigned"
    assignment_reason: str | None = None
    action_items: list[str] = Field(default_factory=list)


class MissionControlErrorRegistrySummary(SQLModel):
    """Aggregate counts for the local OpenClaw error registry."""

    total: int = 0
    open: int = 0
    observed: int = 0
    ignored: int = 0
    fixed: int = 0
    assigned: int = 0
    working: int = 0


class MissionControlErrorRegistryResponse(SQLModel):
    """Read-only Mission Control view over OpenClaw's logged error registry."""

    db_path: str | None = None
    generated_at: str
    summary: MissionControlErrorRegistrySummary = Field(
        default_factory=MissionControlErrorRegistrySummary
    )
    items: list[MissionControlErrorRegistryItem] = Field(default_factory=list)

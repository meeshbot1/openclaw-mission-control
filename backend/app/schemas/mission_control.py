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

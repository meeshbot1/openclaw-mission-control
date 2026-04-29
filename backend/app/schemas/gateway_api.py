"""Schemas for gateway passthrough API request and response payloads."""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (NonEmptyStr,)


class GatewaySessionMessageRequest(SQLModel):
    """Request payload for sending a message into a gateway session."""

    content: NonEmptyStr


class GatewayResolveQuery(SQLModel):
    """Query parameters used to resolve which gateway to target."""

    board_id: str | None = None
    gateway_url: str | None = None
    gateway_token: str | None = None
    gateway_disable_device_pairing: bool | None = None
    gateway_allow_insecure_tls: bool | None = None


class GatewaysStatusResponse(SQLModel):
    """Aggregated gateway status response including session metadata."""

    connected: bool
    gateway_url: str
    sessions_count: int | None = None
    sessions: list[object] | None = None
    main_session: object | None = None
    main_session_error: str | None = None
    error: str | None = None


class GatewaySessionsResponse(SQLModel):
    """Gateway sessions list response payload."""

    sessions: list[object]
    main_session: object | None = None


class GatewaySessionResponse(SQLModel):
    """Single gateway session response payload."""

    session: object


class GatewaySessionHistoryResponse(SQLModel):
    """Gateway session history response payload."""

    history: list[object]


class GatewayCronsResponse(SQLModel):
    """Gateway cron jobs list response payload."""

    crons: list[object]


class GatewayRuntimeEdge(SQLModel):
    """Directed collaboration edge between agent sessions."""

    from_agent: str
    to_agent: str
    relation: str
    session_key: str | None = None


class GatewayRuntimeSessionStatus(SQLModel):
    """Normalized runtime status for an agent or subagent session."""

    agent_id: str
    session_key: str
    status: str
    raw_status: str | None = None
    updated_at: int | None = None
    age_seconds: int | None = None
    channel: str | None = None
    model_provider: str | None = None
    model: str | None = None
    working_on: str | None = None
    with_agents: list[str] = Field(default_factory=list)
    is_subagent: bool = False
    parent_agent_id: str | None = None
    parent_session_key: str | None = None
    label: str | None = None


class GatewayRuntimeOverviewResponse(SQLModel):
    """Gateway runtime overview for status and collaboration dashboards."""

    generated_at_ms: int
    summary: dict[str, int] = Field(default_factory=dict)
    agents: list[GatewayRuntimeSessionStatus] = Field(default_factory=list)
    subagents: list[GatewayRuntimeSessionStatus] = Field(default_factory=list)
    edges: list[GatewayRuntimeEdge] = Field(default_factory=list)


class GatewayCommandsResponse(SQLModel):
    """Gateway command catalog and protocol metadata."""

    protocol_version: int
    methods: list[str]
    events: list[str]

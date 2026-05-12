"""Gateway session query service."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import TRACE_LEVEL
from app.models.boards import Board
from app.models.gateways import Gateway
from app.schemas.gateway_api import (
    GatewayCronsResponse,
    GatewayRuntimeEdge,
    GatewayRuntimeOverviewResponse,
    GatewayRuntimeSessionStatus,
    GatewayResolveQuery,
    GatewaySessionHistoryResponse,
    GatewaySessionMessageRequest,
    GatewaySessionResponse,
    GatewaySessionsResponse,
    GatewaysStatusResponse,
)
from app.services.openclaw.db_service import OpenClawDBService
from app.services.openclaw.error_messages import normalize_gateway_error_message
from app.services.openclaw.gateway_compat import check_gateway_version_compatibility
from app.services.openclaw.gateway_resolver import gateway_client_config, require_gateway_for_board
from app.services.openclaw.gateway_rpc import GatewayConfig as GatewayClientConfig
from app.services.openclaw.gateway_rpc import (
    OpenClawGatewayError,
    ensure_session,
    get_chat_history,
    openclaw_call,
    send_message,
)
from app.services.openclaw.policies import OpenClawAuthorizationPolicy
from app.services.openclaw.shared import GatewayAgentIdentity
from app.services.organizations import require_board_access

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.users import User


@dataclass(frozen=True, slots=True)
class GatewayTemplateSyncQuery:
    """Sync options parsed from query args for gateway template operations."""

    include_main: bool
    lead_only: bool
    reset_sessions: bool
    rotate_tokens: bool
    force_bootstrap: bool
    overwrite: bool
    board_id: UUID | None


class GatewaySessionService(OpenClawDBService):
    """Read/query gateway runtime session state for user-facing APIs."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    def to_resolve_query(
        board_id: str | None,
        gateway_url: str | None,
        gateway_token: str | None,
        gateway_disable_device_pairing: bool | None = None,
        gateway_allow_insecure_tls: bool | None = None,
    ) -> GatewayResolveQuery:
        return GatewayResolveQuery(
            board_id=board_id,
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            gateway_disable_device_pairing=gateway_disable_device_pairing,
            gateway_allow_insecure_tls=gateway_allow_insecure_tls,
        )

    @staticmethod
    def as_object_list(value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set)):
            return list(value)
        if isinstance(value, (str, bytes, dict)):
            return []
        if isinstance(value, Iterable):
            return list(value)
        return []

    @staticmethod
    def _gateway_url_key(value: str | None) -> tuple[str, str, int | None, str] | None:
        raw = (value or "").strip()
        if not raw:
            return None
        parsed = urlparse(raw)
        if not parsed.hostname:
            return None
        scheme = parsed.scheme.lower()
        if scheme == "http":
            scheme = "ws"
        elif scheme == "https":
            scheme = "wss"
        return (
            scheme,
            parsed.hostname.lower(),
            parsed.port,
            (parsed.path or "").rstrip("/"),
        )

    @classmethod
    def _env_gateway_token_for_url(cls, raw_url: str) -> str | None:
        token = settings.openclaw_gateway_token.strip()
        if not token:
            return None
        env_key = cls._gateway_url_key(settings.openclaw_gateway_url)
        raw_key = cls._gateway_url_key(raw_url)
        if env_key is not None and raw_key == env_key:
            return token
        return None

    @staticmethod
    def _extract_agent_id(session_key: str | None) -> str | None:
        if not session_key:
            return None
        parts = session_key.split(":")
        if len(parts) >= 2 and parts[0] == "agent" and parts[1]:
            return parts[1]
        return None

    @staticmethod
    def _as_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return None
        return None

    @classmethod
    def _session_updated_at(cls, session_entry: dict[str, object]) -> int | None:
        return (
            cls._as_int(session_entry.get("updatedAt"))
            or cls._as_int(session_entry.get("endedAt"))
            or cls._as_int(session_entry.get("startedAt"))
        )

    @staticmethod
    def _derive_runtime_status(
        *,
        raw_status: str | None,
        updated_at_ms: int | None,
        now_ms: int,
        aborted_last_run: bool,
    ) -> str:
        normalized = (raw_status or "").strip().lower()
        if aborted_last_run or normalized in {"failed", "error"}:
            return "broken"
        if normalized in {"running", "active", "streaming", "in_progress"}:
            return "working"
        if normalized in {"waiting", "paused", "needs_approval", "needs_input", "queued"}:
            return "waiting"
        if updated_at_ms is None:
            return "unknown"
        age_seconds = max(0, int((now_ms - updated_at_ms) / 1000))
        if age_seconds <= 120:
            return "working"
        return "idle"

    def _build_runtime_row(
        self,
        *,
        session_entry: dict[str, object],
        now_ms: int,
        with_agents: list[str],
    ) -> GatewayRuntimeSessionStatus | None:
        session_key_raw = session_entry.get("key")
        session_key = session_key_raw if isinstance(session_key_raw, str) else None
        agent_id = self._extract_agent_id(session_key)
        if not session_key or not agent_id:
            return None

        updated_at = self._session_updated_at(session_entry)
        age_seconds = (
            max(0, int((now_ms - updated_at) / 1000)) if updated_at is not None else None
        )
        raw_status_value = session_entry.get("status")
        raw_status = raw_status_value if isinstance(raw_status_value, str) else None
        aborted_last_run = bool(session_entry.get("abortedLastRun"))

        parent_key: str | None = None
        parent_key_value = session_entry.get("parentSessionKey")
        if isinstance(parent_key_value, str):
            parent_key = parent_key_value
        spawned_by_value = session_entry.get("spawnedBy")
        if parent_key is None and isinstance(spawned_by_value, str):
            parent_key = spawned_by_value
        parent_agent_id = self._extract_agent_id(parent_key)

        label_value = session_entry.get("label")
        label = label_value if isinstance(label_value, str) else None
        origin = session_entry.get("origin")
        origin_label = (
            origin.get("label")
            if isinstance(origin, dict) and isinstance(origin.get("label"), str)
            else None
        )
        subject_value = session_entry.get("subject")
        subject = subject_value if isinstance(subject_value, str) else None

        working_on = label or origin_label or subject or session_key
        status = self._derive_runtime_status(
            raw_status=raw_status,
            updated_at_ms=updated_at,
            now_ms=now_ms,
            aborted_last_run=aborted_last_run,
        )

        channel_value = session_entry.get("channel")
        channel = channel_value if isinstance(channel_value, str) else None
        model_provider_value = session_entry.get("modelProvider")
        model_provider = (
            model_provider_value if isinstance(model_provider_value, str) else None
        )
        model_value = session_entry.get("model")
        model = model_value if isinstance(model_value, str) else None

        return GatewayRuntimeSessionStatus(
            agent_id=agent_id,
            session_key=session_key,
            status=status,
            raw_status=raw_status,
            updated_at=updated_at,
            age_seconds=age_seconds,
            channel=channel,
            model_provider=model_provider,
            model=model,
            working_on=working_on,
            with_agents=with_agents,
            is_subagent=":subagent:" in session_key,
            parent_agent_id=parent_agent_id,
            parent_session_key=parent_key,
            label=label,
        )

    async def resolve_gateway(
        self,
        params: GatewayResolveQuery,
        *,
        user: User | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[Board | None, GatewayClientConfig, str | None]:
        self.logger.log(
            TRACE_LEVEL,
            "gateway.resolve.start board_id=%s gateway_url=%s",
            params.board_id,
            params.gateway_url,
        )
        if params.gateway_url:
            raw_url = params.gateway_url.strip()
            if not raw_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="board_id or gateway_url is required",
                )
            token = (
                (params.gateway_token or "").strip()
                or self._env_gateway_token_for_url(raw_url)
                or None
            )
            gateway: Gateway | None = None
            can_query_saved_gateway = organization_id is not None and hasattr(self.session, "exec")
            if can_query_saved_gateway and (
                params.gateway_allow_insecure_tls is None
                or params.gateway_disable_device_pairing is None
            ):
                gateway_query = Gateway.objects.filter_by(url=raw_url)
                if organization_id is not None:
                    gateway_query = gateway_query.filter_by(organization_id=organization_id)
                gateway = await gateway_query.first(self.session)
            allow_insecure_tls = (
                params.gateway_allow_insecure_tls
                if params.gateway_allow_insecure_tls is not None
                else (gateway.allow_insecure_tls if gateway is not None else False)
            )
            disable_device_pairing = (
                params.gateway_disable_device_pairing
                if params.gateway_disable_device_pairing is not None
                else (gateway.disable_device_pairing if gateway is not None else False)
            )
            return (
                None,
                GatewayClientConfig(
                    url=raw_url,
                    token=token,
                    allow_insecure_tls=allow_insecure_tls,
                    disable_device_pairing=disable_device_pairing,
                ),
                None,
            )
        if not params.board_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="board_id or gateway_url is required",
            )
        board = await Board.objects.by_id(params.board_id).first(self.session)
        if board is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Board not found",
            )
        if user is not None:
            await require_board_access(self.session, user=user, board=board, write=False)
        gateway = await require_gateway_for_board(self.session, board)
        config = gateway_client_config(gateway)
        main_session = GatewayAgentIdentity.session_key(gateway)
        return (
            board,
            config,
            main_session,
        )

    async def require_gateway(
        self,
        board_id: str | None,
        *,
        user: User | None = None,
    ) -> tuple[Board, GatewayClientConfig, str | None]:
        params = GatewayResolveQuery(board_id=board_id)
        board, config, main_session = await self.resolve_gateway(params, user=user)
        if board is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="board_id is required",
            )
        return board, config, main_session

    async def list_sessions(self, config: GatewayClientConfig) -> list[dict[str, object]]:
        sessions = await openclaw_call("sessions.list", config=config)
        if isinstance(sessions, dict):
            raw_items = self.as_object_list(sessions.get("sessions"))
        else:
            raw_items = self.as_object_list(sessions)
        return [item for item in raw_items if isinstance(item, dict)]

    async def with_main_session(
        self,
        sessions_list: list[dict[str, object]],
        *,
        config: GatewayClientConfig,
        main_session: str | None,
    ) -> list[dict[str, object]]:
        if not main_session or any(item.get("key") == main_session for item in sessions_list):
            return sessions_list
        try:
            await ensure_session(main_session, config=config, label="Gateway Agent")
            return await self.list_sessions(config)
        except OpenClawGatewayError:
            return sessions_list

    @staticmethod
    def _require_same_org(board: Board | None, organization_id: UUID) -> None:
        if board is None:
            return
        OpenClawAuthorizationPolicy.require_board_write_access(
            allowed=board.organization_id == organization_id,
        )

    async def get_status(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaysStatusResponse:
        board, config, main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            compatibility = await check_gateway_version_compatibility(config)
        except OpenClawGatewayError as exc:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=normalize_gateway_error_message(str(exc)),
            )
        if not compatibility.compatible:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=compatibility.message,
            )
        try:
            sessions = await openclaw_call("sessions.list", config=config)
            if isinstance(sessions, dict):
                sessions_list = self.as_object_list(sessions.get("sessions"))
            else:
                sessions_list = self.as_object_list(sessions)
            main_session_entry: object | None = None
            main_session_error: str | None = None
            if main_session:
                try:
                    ensured = await ensure_session(
                        main_session,
                        config=config,
                        label="Gateway Agent",
                    )
                    if isinstance(ensured, dict):
                        main_session_entry = ensured.get("entry") or ensured
                except OpenClawGatewayError as exc:
                    main_session_error = str(exc)
            return GatewaysStatusResponse(
                connected=True,
                gateway_url=config.url,
                sessions_count=len(sessions_list),
                sessions=sessions_list,
                main_session=main_session_entry,
                main_session_error=main_session_error,
            )
        except OpenClawGatewayError as exc:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=normalize_gateway_error_message(str(exc)),
            )

    async def get_sessions(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionsResponse:
        board, config, main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            sessions = await openclaw_call("sessions.list", config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        if isinstance(sessions, dict):
            sessions_list = self.as_object_list(sessions.get("sessions"))
        else:
            sessions_list = self.as_object_list(sessions)

        main_session_entry: object | None = None
        if main_session:
            try:
                ensured = await ensure_session(
                    main_session,
                    config=config,
                    label="Gateway Agent",
                )
                if isinstance(ensured, dict):
                    main_session_entry = ensured.get("entry") or ensured
            except OpenClawGatewayError:
                main_session_entry = None
        return GatewaySessionsResponse(sessions=sessions_list, main_session=main_session_entry)

    async def get_crons(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewayCronsResponse:
        board, config, _main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            payload = await openclaw_call("cron.list", config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        if isinstance(payload, dict):
            for key in ("crons", "jobs", "entries", "items", "list"):
                values = payload.get(key)
                normalized = self.as_object_list(values)
                if normalized:
                    return GatewayCronsResponse(crons=normalized)
            return GatewayCronsResponse(crons=[])
        return GatewayCronsResponse(crons=self.as_object_list(payload))

    async def get_runtime_overview(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewayRuntimeOverviewResponse:
        board, config, _main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            payload = await openclaw_call("sessions.list", config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        if isinstance(payload, dict):
            sessions_list = [
                item
                for item in self.as_object_list(payload.get("sessions"))
                if isinstance(item, dict)
            ]
        else:
            sessions_list = [item for item in self.as_object_list(payload) if isinstance(item, dict)]

        latest_sessions_by_agent: dict[str, dict[str, object]] = {}
        latest_subagent_sessions: dict[str, dict[str, object]] = {}
        edge_keys: set[tuple[str, str, str, str]] = set()
        edges: list[GatewayRuntimeEdge] = []
        collaborators: dict[str, set[str]] = {}

        def add_edge(
            from_agent: str | None,
            to_agent: str | None,
            *,
            relation: str,
            session_key: str | None,
        ) -> None:
            if not from_agent or not to_agent or from_agent == to_agent:
                return
            key = (from_agent, to_agent, relation, session_key or "")
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(
                GatewayRuntimeEdge(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    relation=relation,
                    session_key=session_key,
                )
            )
            collaborators.setdefault(from_agent, set()).add(to_agent)
            collaborators.setdefault(to_agent, set()).add(from_agent)

        for session_entry in sessions_list:
            session_key_value = session_entry.get("key")
            session_key = session_key_value if isinstance(session_key_value, str) else None
            agent_id = self._extract_agent_id(session_key)
            if session_key is None or agent_id is None:
                continue

            updated_at = self._session_updated_at(session_entry) or 0
            is_subagent = ":subagent:" in session_key
            if is_subagent:
                previous = latest_subagent_sessions.get(session_key)
                previous_updated = self._session_updated_at(previous) if previous else None
                if previous is None or (previous_updated or 0) <= updated_at:
                    latest_subagent_sessions[session_key] = session_entry
            else:
                previous = latest_sessions_by_agent.get(agent_id)
                previous_updated = self._session_updated_at(previous) if previous else None
                if previous is None or (previous_updated or 0) <= updated_at:
                    latest_sessions_by_agent[agent_id] = session_entry

            for child in self.as_object_list(session_entry.get("childSessions")):
                if not isinstance(child, str):
                    continue
                child_agent = self._extract_agent_id(child)
                add_edge(agent_id, child_agent, relation="delegates_to", session_key=session_key)

            parent_value = session_entry.get("parentSessionKey")
            if not isinstance(parent_value, str):
                parent_value = (
                    session_entry.get("spawnedBy")
                    if isinstance(session_entry.get("spawnedBy"), str)
                    else None
                )
            if isinstance(parent_value, str):
                parent_agent = self._extract_agent_id(parent_value)
                add_edge(parent_agent, agent_id, relation="spawned", session_key=session_key)

        now_ms = int(time() * 1000)
        agent_rows: list[GatewayRuntimeSessionStatus] = []
        for session_entry in latest_sessions_by_agent.values():
            agent_key_value = session_entry.get("key")
            agent_key = agent_key_value if isinstance(agent_key_value, str) else None
            agent_id = self._extract_agent_id(agent_key)
            with_agents = sorted(collaborators.get(agent_id or "", set()))
            row = self._build_runtime_row(
                session_entry=session_entry,
                now_ms=now_ms,
                with_agents=with_agents,
            )
            if row is not None:
                agent_rows.append(row)
        agent_rows.sort(key=lambda row: row.updated_at or 0, reverse=True)

        subagent_rows: list[GatewayRuntimeSessionStatus] = []
        for session_entry in latest_subagent_sessions.values():
            agent_key_value = session_entry.get("key")
            agent_key = agent_key_value if isinstance(agent_key_value, str) else None
            agent_id = self._extract_agent_id(agent_key)
            with_agents = sorted(collaborators.get(agent_id or "", set()))
            row = self._build_runtime_row(
                session_entry=session_entry,
                now_ms=now_ms,
                with_agents=with_agents,
            )
            if row is not None:
                subagent_rows.append(row)
        subagent_rows.sort(key=lambda row: row.updated_at or 0, reverse=True)

        summary = {
            "agents_total": len(agent_rows),
            "subagents_total": len(subagent_rows),
            "edges_total": len(edges),
            "working": 0,
            "idle": 0,
            "waiting": 0,
            "broken": 0,
            "unknown": 0,
        }
        for row in [*agent_rows, *subagent_rows]:
            summary[row.status] = summary.get(row.status, 0) + 1

        return GatewayRuntimeOverviewResponse(
            generated_at_ms=now_ms,
            summary=summary,
            agents=agent_rows,
            subagents=subagent_rows,
            edges=edges,
        )

    async def get_session(
        self,
        *,
        session_id: str,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionResponse:
        board, config, main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            sessions_list = await self.list_sessions(config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        sessions_list = await self.with_main_session(
            sessions_list,
            config=config,
            main_session=main_session,
        )
        session_entry = next(
            (item for item in sessions_list if item.get("key") == session_id), None
        )
        if session_entry is None and main_session and session_id == main_session:
            try:
                ensured = await ensure_session(
                    main_session,
                    config=config,
                    label="Gateway Agent",
                )
                if isinstance(ensured, dict):
                    session_entry = ensured.get("entry") or ensured
            except OpenClawGatewayError:
                session_entry = None
        if session_entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        return GatewaySessionResponse(session=session_entry)

    async def get_session_history(
        self,
        *,
        session_id: str,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionHistoryResponse:
        board, config, _ = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            history = await get_chat_history(session_id, config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        if isinstance(history, dict) and isinstance(history.get("messages"), list):
            return GatewaySessionHistoryResponse(history=history["messages"])
        return GatewaySessionHistoryResponse(history=self.as_object_list(history))

    async def send_session_message(
        self,
        *,
        session_id: str,
        payload: GatewaySessionMessageRequest,
        board_id: str | None,
        organization_id: UUID,
        user: User | None,
    ) -> None:
        board, config, main_session = await self.require_gateway(board_id, user=user)
        self._require_same_org(board, organization_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        await require_board_access(self.session, user=user, board=board, write=True)
        try:
            if main_session and session_id == main_session:
                await ensure_session(main_session, config=config, label="Gateway Agent")
            await send_message(payload.content, session_key=session_id, config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

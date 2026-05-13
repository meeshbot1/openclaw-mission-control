#!/usr/bin/env python3
"""Mission Control stability checklist runner.

This script is designed for the disabled nightly OpenClaw cron job. It performs
bounded, non-destructive checks and emits a JSON report that includes action
items for failures. It intentionally never prints bearer tokens, gateway tokens,
database passwords, or secret-bearing URLs.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000"
DEFAULT_GATEWAY_HTTP_URL = "http://127.0.0.1:18789"
REQUIREMENTS_DOC = (
    PROJECT_ROOT / "docs/operations/mission-control-stability-test-requirements.md"
)
DASHBOARD_DETAIL_CARD_IDS = (
    "online-agents",
    "tasks-in-progress",
    "error-rate",
    "completion-speed",
    "workload",
    "throughput",
    "gateway-health",
    "agents-and-teams",
    "collaboration-graph",
    "cron-jobs",
    "boards-tasks-feeds",
    "codex-teams",
    "worker-panes",
    "runtime-gateways",
    "codex-threads",
    "scan-roots",
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    evidence: dict[str, Any]
    action_items: list[str]


def read_env_files() -> dict[str, str]:
    values: dict[str, str] = {}
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "backend/.env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip("'\""))
    values.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.startswith(("LOCAL_AUTH_", "OPENCLAW_", "MISSION_CONTROL_"))
        }
    )
    return values


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    safe_pairs = []
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        if (
            "token" in key.lower()
            or "password" in key.lower()
            or "secret" in key.lower()
        ):
            safe_pairs.append((key, "<redacted>"))
        else:
            safe_pairs.append((key, value))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(safe_pairs),
            parsed.fragment,
        )
    )


def normalize_gateway_ws_url(value: str | None) -> str:
    raw = (value or DEFAULT_GATEWAY_HTTP_URL).strip()
    if raw.startswith("http://"):
        return "ws://" + raw.removeprefix("http://")
    if raw.startswith("https://"):
        return "wss://" + raw.removeprefix("https://")
    if raw.startswith(("ws://", "wss://")):
        return raw
    return f"ws://{raw}"


def gateway_http_url(value: str | None) -> str:
    raw = (value or DEFAULT_GATEWAY_HTTP_URL).strip()
    if raw.startswith("ws://"):
        return "http://" + raw.removeprefix("ws://")
    if raw.startswith("wss://"):
        return "https://" + raw.removeprefix("wss://")
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


def http_request(
    url: str,
    *,
    token: str | None = None,
    timeout: float = 10.0,
    method: str = "GET",
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any, str]:
    headers = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                return response.status, json.loads(body), ""
            return response.status, body[:500], ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body[:500], str(exc)
    except Exception as exc:  # noqa: BLE001 - report operational failure as evidence
        return 0, None, str(exc)


def add_result(
    results: list[CheckResult],
    name: str,
    ok: bool,
    evidence: dict[str, Any],
    *actions: str,
) -> None:
    results.append(
        CheckResult(
            name=name,
            ok=ok,
            evidence=evidence,
            action_items=[item for item in actions if item],
        )
    )


def run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> CheckResult:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        output = completed.stdout[-4000:]
        ok = completed.returncode == 0
        return CheckResult(
            name=name,
            ok=ok,
            evidence={
                "command": " ".join(command),
                "cwd": str(cwd),
                "returncode": completed.returncode,
                "duration_seconds": round(time.time() - started, 2),
                "output_tail": output,
            },
            action_items=(
                [] if ok else [f"Investigate failed command: {' '.join(command)}"]
            ),
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=name,
            ok=False,
            evidence={
                "command": " ".join(command),
                "cwd": str(cwd),
                "timeout_seconds": timeout_seconds,
                "duration_seconds": round(time.time() - started, 2),
                "output_tail": (
                    (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else ""
                ),
            },
            action_items=[
                f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
            ],
        )


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def authenticated_url(
    base_url: str, path: str, query: dict[str, str] | None = None
) -> str:
    url = base_url.rstrip("/") + path
    if query:
        return url + "?" + urllib.parse.urlencode(query)
    return url


def collect_live_checks(
    args: argparse.Namespace, env: dict[str, str]
) -> list[CheckResult]:
    results: list[CheckResult] = []
    backend_url = args.backend_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    auth_token = env.get("LOCAL_AUTH_TOKEN")
    gateway_ws = normalize_gateway_ws_url(
        args.gateway_url or env.get("OPENCLAW_GATEWAY_URL")
    )
    gateway_http = gateway_http_url(args.gateway_url or env.get("OPENCLAW_GATEWAY_URL"))
    gateway_token = env.get("OPENCLAW_GATEWAY_TOKEN")

    add_result(
        results,
        "requirements_document_present",
        REQUIREMENTS_DOC.exists(),
        {"path": str(REQUIREMENTS_DOC), "exists": REQUIREMENTS_DOC.exists()},
        (
            f"Restore or create {REQUIREMENTS_DOC}"
            if not REQUIREMENTS_DOC.exists()
            else ""
        ),
    )

    for name, host, port in (
        ("postgres_port", "127.0.0.1", int(env.get("POSTGRES_PORT", "5432"))),
        ("redis_port", "127.0.0.1", 6379),
        ("backend_port", "127.0.0.1", urllib.parse.urlsplit(backend_url).port or 8000),
        (
            "frontend_port",
            "127.0.0.1",
            urllib.parse.urlsplit(frontend_url).port or 3000,
        ),
        (
            "gateway_port",
            "127.0.0.1",
            urllib.parse.urlsplit(gateway_http).port or 18789,
        ),
    ):
        ok = port_open(host, port)
        add_result(
            results,
            name,
            ok,
            {"host": host, "port": port, "open": ok},
            f"Start or repair service listening on {host}:{port}" if not ok else "",
        )

    for path in ("/healthz", "/readyz"):
        status, body, error = http_request(
            backend_url + path, timeout=args.http_timeout
        )
        add_result(
            results,
            f"backend{path}",
            status == 200,
            {"status": status, "body": body, "error": error},
            (
                f"Restart or inspect backend because {path} did not return 200"
                if status != 200
                else ""
            ),
        )

    cors_origins = [
        origin.strip()
        for origin in env.get("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    for origin in cors_origins[:8]:
        status, body, error = http_request(
            backend_url + "/api/v1/gateways/mission-control/errors?status=open&limit=1",
            method="OPTIONS",
            timeout=args.http_timeout,
            extra_headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        add_result(
            results,
            f"cors_preflight_{urllib.parse.urlsplit(origin).netloc or origin}",
            status == 200,
            {"origin": origin, "status": status, "body": body, "error": error},
            (
                f"Restart backend with refreshed CORS_ORIGINS or add origin {origin}"
                if status != 200
                else ""
            ),
        )

    status, body, error = http_request(
        frontend_url + "/dashboard", timeout=args.http_timeout
    )
    add_result(
        results,
        "frontend_dashboard",
        status == 200,
        {"status": status, "body_type": type(body).__name__, "error": error},
        (
            "Restart or inspect frontend because /dashboard did not return 200"
            if status != 200
            else ""
        ),
    )

    frontend_routes = [
        ("frontend_errors_view", "/dashboard/errors"),
        *(
            (f"frontend_detail_{card_id}", f"/dashboard/details/{card_id}")
            for card_id in DASHBOARD_DETAIL_CARD_IDS
        ),
        (
            "frontend_cron_dashboard",
            f"/gateways/{urllib.parse.quote(args.cron_page_gateway_id)}/crons",
        ),
    ]
    for name, path in frontend_routes:
        status, body, error = http_request(
            frontend_url + path, timeout=args.frontend_timeout
        )
        add_result(
            results,
            name,
            status == 200,
            {
                "status": status,
                "path": path,
                "body_type": type(body).__name__,
                "error": error,
            },
            f"Repair frontend route {path}; expected HTTP 200" if status != 200 else "",
        )

    status, body, error = http_request(
        gateway_http.rstrip("/") + "/health", timeout=args.http_timeout
    )
    add_result(
        results,
        "gateway_health",
        status == 200,
        {"status": status, "body": body, "error": error},
        (
            "Restart or inspect OpenClaw gateway because /health did not return 200"
            if status != 200
            else ""
        ),
    )

    if not auth_token:
        add_result(
            results,
            "local_auth_token_present",
            False,
            {"present": False},
            "Set LOCAL_AUTH_TOKEN so authenticated stability checks can run",
        )
        return results

    gateway_query = {"gateway_url": gateway_ws}
    if gateway_token:
        gateway_query["gateway_token"] = gateway_token

    api_checks = [
        ("metrics_dashboard", "/api/v1/metrics/dashboard", None),
        ("gateway_status", "/api/v1/gateways/status", gateway_query),
        (
            "gateway_runtime_overview",
            "/api/v1/gateways/runtime-overview",
            gateway_query,
        ),
        ("gateway_crons", "/api/v1/gateways/crons", gateway_query),
        (
            "mission_control_error_registry",
            "/api/v1/gateways/mission-control/errors",
            {"status": "open", "limit": "200"},
        ),
    ]
    for name, path, query in api_checks:
        url = authenticated_url(backend_url, path, query)
        status, body, error = http_request(
            url, token=auth_token, timeout=args.http_timeout
        )
        evidence: dict[str, Any] = {
            "status": status,
            "url": redact_url(url.replace(auth_token, "<redacted>")),
            "error": error,
        }
        ok = status == 200
        if isinstance(body, dict):
            if name == "gateway_crons":
                crons = body.get("crons", [])
                evidence.update(
                    {
                        "cron_count": len(crons) if isinstance(crons, list) else None,
                        "has_crons": bool(crons),
                    }
                )
                ok = ok and isinstance(crons, list)
            elif name == "mission_control_error_registry":
                items = body.get("items", [])
                unassigned = [
                    item.get("id")
                    for item in items
                    if isinstance(item, dict) and not item.get("assigned_agent_id")
                ]
                actionless = [
                    item.get("id")
                    for item in items
                    if isinstance(item, dict)
                    and item.get("status") == "open"
                    and not item.get("action_items")
                ]
                missing_schedule_status = [
                    item.get("id")
                    for item in items
                    if isinstance(item, dict)
                    and item.get("status") == "open"
                    and not item.get("remediation_schedule_status")
                ]
                cron_without_schedule = [
                    item.get("id")
                    for item in items
                    if isinstance(item, dict)
                    and item.get("status") == "open"
                    and item.get("assigned_cron_id")
                    and not item.get("assigned_cron_schedule")
                ]
                evidence.update(
                    {
                        "db_path": body.get("db_path"),
                        "summary": body.get("summary"),
                        "items": len(items) if isinstance(items, list) else None,
                        "unassigned_open_ids": unassigned[:20],
                        "actionless_open_ids": actionless[:20],
                        "missing_schedule_status_ids": missing_schedule_status[:20],
                        "cron_without_schedule_ids": cron_without_schedule[:20],
                    }
                )
                ok = (
                    ok
                    and not unassigned
                    and not actionless
                    and not missing_schedule_status
                    and not cron_without_schedule
                )
        add_result(
            results,
            name,
            ok,
            evidence,
            f"Investigate {path}; expected HTTP 200" if status != 200 else "",
            (
                "Assign all visible open error rows to an agent or cron"
                if name == "mission_control_error_registry"
                and isinstance(body, dict)
                and evidence.get("unassigned_open_ids")
                else ""
            ),
            (
                "Add action items for visible open error rows"
                if name == "mission_control_error_registry"
                and isinstance(body, dict)
                and evidence.get("actionless_open_ids")
                else ""
            ),
            (
                "Expose remediation schedule status for visible open error rows"
                if name == "mission_control_error_registry"
                and isinstance(body, dict)
                and evidence.get("missing_schedule_status_ids")
                else ""
            ),
            (
                "Expose schedule metadata for visible assigned remediation crons"
                if name == "mission_control_error_registry"
                and isinstance(body, dict)
                and evidence.get("cron_without_schedule_ids")
                else ""
            ),
        )

    return results


def collect_targeted_tests(args: argparse.Namespace) -> list[CheckResult]:
    if not args.include_targeted_tests:
        return []
    return [
        run_command(
            "backend_py_compile",
            [
                "uv",
                "run",
                "python",
                "-m",
                "py_compile",
                "app/schemas/mission_control.py",
                "app/services/openclaw/mission_control_ops_service.py",
                "app/api/gateways.py",
            ],
            cwd=PROJECT_ROOT / "backend",
            timeout_seconds=120,
        ),
        run_command(
            "backend_mission_control_live_api_tests",
            ["uv", "run", "pytest", "tests/test_mission_control_live_api.py"],
            cwd=PROJECT_ROOT / "backend",
            timeout_seconds=180,
        ),
        run_command(
            "frontend_typecheck",
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=PROJECT_ROOT / "frontend",
            timeout_seconds=240,
        ),
        run_command(
            "frontend_targeted_vitest",
            [
                "npx",
                "vitest",
                "run",
                "--passWithNoTests",
                "--maxWorkers=1",
                "--no-file-parallelism",
                "src/lib/gateway-crons.test.ts",
                "src/app/gateways/[gatewayId]/crons/page.test.tsx",
                "src/app/dashboard/page.test.tsx",
            ],
            cwd=PROJECT_ROOT / "frontend",
            timeout_seconds=180,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Mission Control stability checks."
    )
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--gateway-url", default=None)
    parser.add_argument("--http-timeout", type=float, default=12.0)
    parser.add_argument("--frontend-timeout", type=float, default=30.0)
    parser.add_argument("--cron-page-gateway-id", default="local")
    parser.add_argument("--include-targeted-tests", action="store_true")
    args = parser.parse_args()

    env = read_env_files()
    checks = collect_live_checks(args, env) + collect_targeted_tests(args)
    failures = [check for check in checks if not check.ok]
    report = {
        "status": "ok" if not failures else "failed",
        "generated_at_ms": int(time.time() * 1000),
        "project_root": str(PROJECT_ROOT),
        "requirements_doc": str(REQUIREMENTS_DOC),
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
        },
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "evidence": check.evidence,
                "action_items": check.action_items,
            }
            for check in checks
        ],
        "action_items": [item for check in failures for item in check.action_items],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEOUT_SECONDS="${OPENCLAW_FRONTEND_BUILD_TIMEOUT_SECONDS:-300}"
MIN_AVAILABLE_KB="${OPENCLAW_FRONTEND_BUILD_MIN_AVAILABLE_KB:-2097152}"
MEMORY_MAX="${OPENCLAW_FRONTEND_BUILD_MEMORY_MAX:-1200M}"
CPU_QUOTA="${OPENCLAW_FRONTEND_BUILD_CPU_QUOTA:-150%}"
MAX_OLD_SPACE_MB="${OPENCLAW_FRONTEND_BUILD_MAX_OLD_SPACE_MB:-512}"

available_kb="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if [[ "${OPENCLAW_ALLOW_LOW_MEMORY_BUILD:-0}" != "1" ]] && (( available_kb > 0 && available_kb < MIN_AVAILABLE_KB )); then
  echo "Refusing frontend build: MemAvailable=${available_kb}kB is below ${MIN_AVAILABLE_KB}kB." >&2
  echo "Set OPENCLAW_ALLOW_LOW_MEMORY_BUILD=1 only when the host has enough headroom." >&2
  exit 75
fi

export NEXT_TELEMETRY_DISABLED="${NEXT_TELEMETRY_DISABLED:-1}"
export NODE_OPTIONS="${NODE_OPTIONS:-} --max-old-space-size=${MAX_OLD_SPACE_MB}"

cmd=(timeout "$TIMEOUT_SECONDS" bash scripts/with_node.sh --cwd frontend npx next build)

cd "$ROOT"

if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  exec systemd-run --user --scope --quiet \
    --property="MemoryMax=${MEMORY_MAX}" \
    --property="CPUQuota=${CPU_QUOTA}" \
    --property="IOWeight=${OPENCLAW_FRONTEND_BUILD_IO_WEIGHT:-50}" \
    --working-directory="$ROOT" \
    /usr/bin/env \
      NEXT_TELEMETRY_DISABLED="$NEXT_TELEMETRY_DISABLED" \
      NODE_OPTIONS="$NODE_OPTIONS" \
      "${cmd[@]}"
fi

if command -v ionice >/dev/null 2>&1; then
  exec ionice -c 3 nice -n "${OPENCLAW_FRONTEND_BUILD_NICE:-10}" "${cmd[@]}"
fi

exec nice -n "${OPENCLAW_FRONTEND_BUILD_NICE:-10}" "${cmd[@]}"

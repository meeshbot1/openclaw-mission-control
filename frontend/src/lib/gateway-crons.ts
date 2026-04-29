export type GatewayCronView = {
  id: string;
  name: string;
  schedule: string;
  timezone: string | null;
  enabled: boolean | null;
  enabledLabel: string;
  target: string;
  agentId: string | null;
  model: string | null;
  purpose: string;
  lastRunAtMs: number | null;
  lastRunStatus: string | null;
  nextRunAtMs: number | null;
  lastDurationMs: number | null;
};

const asRecord = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
};

const asString = (value: unknown): string | null => {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length ? trimmed : null;
  }
  return null;
};

const asBoolean = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  return null;
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
};

const extractPurpose = (message: string | null): string => {
  if (!message) return "—";
  const firstLine = message
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  if (!firstLine) return "—";
  if (firstLine.length <= 140) return firstLine;
  return `${firstLine.slice(0, 137)}...`;
};

const scheduleFromRecord = (
  record: Record<string, unknown>,
): { schedule: string; timezone: string | null } => {
  const scheduleRaw = record.schedule;
  if (typeof scheduleRaw === "string" && scheduleRaw.trim().length) {
    return { schedule: scheduleRaw.trim(), timezone: asString(record.tz) };
  }
  if (scheduleRaw && typeof scheduleRaw === "object") {
    const scheduleObj = asRecord(scheduleRaw);
    const expr = asString(scheduleObj.expr);
    const kind = asString(scheduleObj.kind);
    const tz = asString(scheduleObj.tz);
    if (expr && kind) {
      return { schedule: `${kind}: ${expr}`, timezone: tz };
    }
    if (expr) {
      return { schedule: expr, timezone: tz };
    }
  }
  const cron = asString(record.cron);
  if (cron) return { schedule: cron, timezone: asString(record.tz) };
  const expression = asString(record.expression);
  if (expression) return { schedule: expression, timezone: asString(record.tz) };
  return { schedule: "—", timezone: null };
};

export const toGatewayCronView = (value: unknown): GatewayCronView => {
  const record = asRecord(value);
  const payload = asRecord(record.payload);
  const state = asRecord(record.state);
  const delivery = asRecord(record.delivery);

  const id = asString(record.id) ?? asString(record.key) ?? "—";
  const name = asString(record.name) ?? asString(record.label) ?? id;
  const { schedule, timezone } = scheduleFromRecord(record);
  const enabled =
    asBoolean(record.enabled) ??
    asBoolean(record.active) ??
    asBoolean(state.enabled) ??
    null;
  const enabledLabel =
    enabled === null ? "Unknown" : enabled ? "Enabled" : "Disabled";
  const target =
    asString(record.target) ??
    asString(record.sessionKey) ??
    asString(record.session_key) ??
    asString(delivery.to) ??
    "—";
  const agentId =
    asString(record.agentId) ??
    asString(payload.agentId) ??
    asString(record.agent) ??
    null;
  const model =
    asString(payload.model) ??
    asString(record.model) ??
    asString(state.model) ??
    null;
  const purpose = extractPurpose(asString(payload.message));
  const lastRunAtMs =
    asNumber(state.lastRunAtMs) ??
    asNumber(state.lastRunAt) ??
    asNumber(record.lastRunAtMs) ??
    null;
  const lastRunStatus =
    asString(state.lastRunStatus) ??
    asString(state.lastStatus) ??
    asString(record.lastRunStatus) ??
    null;
  const nextRunAtMs =
    asNumber(state.nextRunAtMs) ?? asNumber(record.nextRunAtMs) ?? null;
  const lastDurationMs =
    asNumber(state.lastDurationMs) ?? asNumber(record.lastDurationMs) ?? null;

  return {
    id,
    name,
    schedule,
    timezone,
    enabled,
    enabledLabel,
    target,
    agentId,
    model,
    purpose,
    lastRunAtMs,
    lastRunStatus,
    nextRunAtMs,
    lastDurationMs,
  };
};


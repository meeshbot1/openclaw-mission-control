import { describe, expect, it } from "vitest";

import { toGatewayCronView } from "./gateway-crons";

describe("toGatewayCronView", () => {
  it("normalizes nested schedule and runtime fields", () => {
    const record = toGatewayCronView({
      id: "morning-briefing-001",
      name: "Morning Briefing",
      agentId: "main",
      schedule: {
        kind: "cron",
        expr: "0 8 * * *",
        tz: "America/Chicago",
      },
      payload: {
        model: "ollama/qwen3.5:9b",
        message:
          "Good morning briefing for Amish.\n\n1) Read priorities.\n2) Check reminders.",
      },
      delivery: {
        to: "-1003616868447",
      },
      state: {
        lastRunAtMs: 1776862801395,
        lastRunStatus: "ok",
        nextRunAtMs: 1776949200000,
      },
      enabled: true,
    });

    expect(record.id).toBe("morning-briefing-001");
    expect(record.name).toBe("Morning Briefing");
    expect(record.schedule).toBe("cron: 0 8 * * *");
    expect(record.timezone).toBe("America/Chicago");
    expect(record.enabled).toBe(true);
    expect(record.enabledLabel).toBe("Enabled");
    expect(record.agentId).toBe("main");
    expect(record.model).toBe("ollama/qwen3.5:9b");
    expect(record.target).toBe("-1003616868447");
    expect(record.purpose).toBe("Good morning briefing for Amish.");
    expect(record.lastRunStatus).toBe("ok");
  });

  it("falls back safely when optional fields are missing", () => {
    const record = toGatewayCronView({
      key: "legacy-job-1",
      expression: "*/5 * * * *",
      active: false,
    });

    expect(record.id).toBe("legacy-job-1");
    expect(record.name).toBe("legacy-job-1");
    expect(record.schedule).toBe("*/5 * * * *");
    expect(record.enabled).toBe(false);
    expect(record.enabledLabel).toBe("Disabled");
    expect(record.target).toBe("—");
    expect(record.purpose).toBe("—");
    expect(record.model).toBeNull();
    expect(record.lastRunAtMs).toBeNull();
  });
});


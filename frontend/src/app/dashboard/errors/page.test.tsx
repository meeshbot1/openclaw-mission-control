import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import DashboardErrorsPage from "./page";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/auth/clerk", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: () => null,
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/components/auth/SignedOutPanel", () => ({
  SignedOutPanel: ({ message }: { message: string }) => <div>{message}</div>,
}));

vi.mock("@/components/organisms/DashboardSidebar", () => ({
  DashboardSidebar: () => <div data-testid="dashboard-sidebar" />,
}));

vi.mock("@/components/templates/DashboardShell", () => ({
  DashboardShell: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => (
    <button disabled={disabled} onClick={onClick}>
      {children}
    </button>
  ),
}));

vi.mock("@/api/mutator", () => ({
  ApiError: class ApiError extends Error {},
  customFetch: vi.fn(),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>(
    "@tanstack/react-query",
  );
  return {
    ...actual,
    useQuery: () => ({
      data: {
        db_path: "/home/amish/.openclaw/logs/openclaw-error-registry.db",
        generated_at: "2026-05-13T18:00:00Z",
        summary: {
          total: 1,
          open: 1,
          observed: 0,
          ignored: 0,
          fixed: 0,
          assigned: 1,
          working: 0,
        },
        items: [
          {
            id: 43119,
            source_kind: "file",
            source: "/home/amish/.openclaw/logs/gateway.log",
            event_ts: "2026-05-12T23:28:17Z",
            level: "error",
            service: "gateway",
            category: "gateway-token-drift",
            fix_type: "gateway-token-repair",
            message: "gateway token mismatch",
            status: "open",
            fix_attempts: 0,
            last_seen_at: "2026-05-12T23:34:23Z",
            assigned_agent_id: "ops",
            assigned_cron_id: "gateway-health-check",
            assigned_cron_name: "gateway-health-check",
            assigned_cron_schedule: "cron: */10 * * * *",
            assigned_cron_timezone: "America/Chicago",
            assigned_cron_enabled: true,
            assigned_cron_next_run_at_ms: 1770000900000,
            assigned_cron_last_run_at_ms: 1770000000000,
            assigned_cron_last_run_status: "ok",
            remediation_schedule_status: "scheduled",
            assignment_state: "queued",
            assignment_reason: "gateway-token-repair",
            action_items: ["Verify gateway tokens before the next run."],
          },
        ],
      },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    }),
  };
});

describe("/dashboard/errors", () => {
  it("shows when the assigned cron is scheduled to work an error", () => {
    render(<DashboardErrorsPage />);

    expect(screen.getByText(/scheduled fix/i)).toBeInTheDocument();
    expect(screen.getByText(/^Next /)).toBeInTheDocument();
    expect(
      screen.getByText(/gateway-health-check.*cron: \*\/10/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/queued/i)).toBeInTheDocument();
  });
});

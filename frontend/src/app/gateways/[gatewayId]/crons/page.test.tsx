import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import GatewayCronDashboardPage from "./page";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ gatewayId: "gateway-1" }),
  useRouter: () => ({
    push,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: () => ({ isAdmin: true }),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>(
    "@tanstack/react-query",
  );
  return {
    ...actual,
    useQuery: () => ({
      data: {
        crons: [
          {
            id: "mc-heartbeat",
            name: "Mission Control readiness heartbeat",
            schedule: { kind: "cron", expr: "*/15 * * * *", tz: "America/Chicago" },
            payload: { message: "Mission Control readiness check" },
            agentId: "dev-projects-mission-control",
            enabled: true,
            state: {
              lastRunStatus: "failed",
              lastRunAtMs: 1770000000000,
              nextRunAtMs: 1770000900000,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    }),
  };
});

vi.mock("@/components/templates/DashboardPageLayout", () => ({
  DashboardPageLayout: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
}));

vi.mock("@/api/mutator", () => ({
  ApiError: class ApiError extends Error {},
  customFetch: vi.fn(),
}));

vi.mock("@/api/generated/gateways/gateways", () => ({
  useGetGatewayApiV1GatewaysGatewayIdGet: () => ({
    data: {
      status: 200,
      data: {
        id: "gateway-1",
        name: "Local OpenClaw Gateway",
        url: "ws://127.0.0.1:18789",
        token: "secret-token",
        disable_device_pairing: true,
        allow_insecure_tls: false,
      },
    },
    isLoading: false,
    error: null,
  }),
}));

describe("/gateways/[gatewayId]/crons", () => {
  it("renders failing cron summary and job details", () => {
    render(<GatewayCronDashboardPage />);

    expect(screen.getByRole("heading", { name: /local openclaw gateway cron dashboard/i })).toBeInTheDocument();
    expect(screen.getByText(/total jobs/i)).toBeInTheDocument();
    expect(screen.getByText(/mission control readiness heartbeat/i)).toBeInTheDocument();
    expect(screen.getByText(/failing last run/i)).toBeInTheDocument();
    expect(screen.getAllByText(/failed/i).length).toBeGreaterThan(0);
  });
});

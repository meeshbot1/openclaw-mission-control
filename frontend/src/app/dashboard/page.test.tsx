import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import DashboardPage from "./page";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { QueryProvider } from "@/components/providers/QueryProvider";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({
    push,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("next/link", () => {
  type LinkProps = React.PropsWithChildren<{
    href: string | { pathname?: string };
  }> &
    Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

  return {
    default: ({ href, children, ...props }: LinkProps) => (
      <a href={typeof href === "string" ? href : "#"} {...props}>
        {children}
      </a>
    ),
  };
});

vi.mock("@/auth/clerk", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/components/organisms/DashboardSidebar", () => ({
  DashboardSidebar: () => <div data-testid="dashboard-sidebar" />,
}));

vi.mock("@/components/templates/DashboardShell", () => ({
  DashboardShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/auth/SignedOutPanel", () => ({
  SignedOutPanel: ({ message }: { message: string }) => <div>{message}</div>,
}));

vi.mock("@/components/atoms/Markdown", () => ({
  Markdown: ({ content }: { content: string }) => <span>{content}</span>,
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useListBoardsApiV1BoardsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/api/generated/gateways/gateways", () => ({
  useListGatewaysApiV1GatewaysGet: () => ({
    data: {
      status: 200,
      data: {
        items: [
          {
            id: "gateway-1",
            name: "Local OpenClaw Gateway",
            url: "ws://127.0.0.1:18789",
            workspace_root: "/home/amish/.openclaw",
          },
        ],
      },
    },
    isLoading: false,
  }),
  gatewaysStatusApiV1GatewaysStatusGet: vi.fn().mockResolvedValue({
    status: 200,
    data: {
      connected: true,
      gateway_url: "ws://127.0.0.1:18789",
      sessions_count: 0,
      sessions: [],
      main_session: null,
      main_session_error: null,
      error: null,
    },
  }),
}));

vi.mock("@/api/generated/agents/agents", () => ({
  useListAgentsApiV1AgentsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/api/generated/activity/activity", () => ({
  useListActivityApiV1ActivityGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/api/generated/metrics/metrics", () => ({
  useDashboardMetricsApiV1MetricsDashboardGet: () => ({
    data: {
      status: 200,
      data: {
        kpis: {
          active_agents: 0,
          tasks_in_progress: 0,
          inbox_tasks: 0,
          in_progress_tasks: 0,
          review_tasks: 0,
          done_tasks: 0,
          error_rate_pct: 0,
        },
        throughput: {
          primary: { points: [] },
        },
        pending_approvals: { items: [], total: 0 },
      },
    },
    isLoading: false,
    error: null,
  }),
}));

describe("/dashboard gateway visibility", () => {
  beforeEach(() => {
    push.mockReset();
  });

  it("does not claim gateways are unconfigured when a gateway exists but no board is linked", async () => {
    render(
      <AuthProvider>
        <QueryProvider>
          <DashboardPage />
        </QueryProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/not linked to a board yet/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/session visibility may be limited/i)).toBeInTheDocument();
    expect(screen.getByText(/no active sessions detected/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/no gateways are configured for any board yet/i),
    ).not.toBeInTheDocument();
  });
});

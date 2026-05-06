import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import DashboardPage from "./page";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { customFetch } from "@/api/mutator";

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

vi.mock("@/api/mutator", () => ({
  ApiError: class ApiError extends Error {
    status = 500;
    data = null;
  },
  customFetch: vi.fn(),
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
            token: "gateway-token",
            disable_device_pairing: true,
            allow_insecure_tls: false,
          },
        ],
      },
    },
    isLoading: false,
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
    vi.mocked(customFetch).mockImplementation(async (url: string) => {
      if (url.startsWith("/api/v1/gateways/status")) {
        return {
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
          headers: new Headers(),
        };
      }
      if (url.startsWith("/api/v1/gateways/runtime-overview")) {
        return {
          status: 200,
          data: {
            generated_at_ms: Date.now(),
            summary: {
              agents_total: 24,
              subagents_total: 14,
              edges_total: 13,
              working: 2,
              idle: 34,
              waiting: 0,
              broken: 2,
              unknown: 0,
            },
            agents: [
              {
                agent_id: "main",
                session_key: "agent:main:main",
                status: "idle",
                model: "gpt-5.4",
                with_agents: [],
              },
            ],
            subagents: [],
            edges: [{ from_agent: "main", to_agent: "research", relation: "handoff" }],
          },
          headers: new Headers(),
        };
      }
      if (url.startsWith("/api/v1/gateways/crons")) {
        return {
          status: 200,
          data: {
            crons: [
              {
                id: "cron-1",
                name: "gateway-health-check",
                enabled: true,
                payload: { model: "openai-codex/gpt-5.4" },
                state: { lastRunStatus: "ok" },
              },
            ],
          },
          headers: new Headers(),
        };
      }
      if (url.startsWith("/api/v1/gateways/mission-control/live")) {
        return {
          status: 200,
          data: {
            generated_at: "2026-05-06T01:12:00Z",
            scanned_roots: ["/home/amish/.openclaw"],
            summary: {
              teams_total: 1,
              tasks_total: 3,
              workers_total: 2,
              workers_active: 1,
              gateways_total: 1,
              gateways_ok: 1,
            },
            teams: [
              {
                team_name: "project-webapp-team",
                task: "Build the customer portal",
                state_root: "/home/amish/.openclaw/.omx/state",
                project_root: "/home/amish/.openclaw/workspace/projects/customer-portal",
                tasks_total: 3,
                workers_total: 2,
                task_counts: {
                  pending: 1,
                  in_progress: 1,
                  completed: 1,
                  failed: 0,
                  blocked: 0,
                  other: 0,
                },
                tasks: [
                  {
                    task_id: "1",
                    subject: "Implement landing page",
                    status: "in_progress",
                    owner: "worker-1",
                    role: "executor",
                  },
                  {
                    task_id: "2",
                    subject: "Verify deployment scripts",
                    status: "pending",
                    owner: "worker-2",
                    role: "verifier",
                  },
                ],
                workers: [
                  {
                    name: "worker-1",
                    role: "executor",
                    pane_id: "%42",
                    state: "busy",
                    task_id: "1",
                    alive: true,
                  },
                  {
                    name: "worker-2",
                    role: "verifier",
                    pane_id: "%43",
                    state: "waiting",
                    task_id: "2",
                    alive: true,
                  },
                ],
                recent_messages: [
                  {
                    message_id: "msg-1",
                    from_worker: "worker-1",
                    to_worker: "leader-fixed",
                    body: "Landing page shell is implemented",
                    created_at: "2026-05-06T01:12:00Z",
                  },
                ],
                recent_events: [],
              },
            ],
            gateways: [
              {
                gateway_id: "gateway-1",
                gateway_name: "Local OpenClaw Gateway",
                gateway_url: "ws://127.0.0.1:18789",
                workspace_root: "/home/amish/.openclaw",
                ok: true,
                generated_at_ms: Date.now(),
                summary: { agents_total: 1 },
                agents: [],
                subagents: [],
              },
            ],
          },
          headers: new Headers(),
        };
      }
      throw new Error(`Unexpected URL: ${url}`);
    });
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
    expect(screen.getByText(/Runtime Coverage/i)).toBeInTheDocument();
    expect(screen.getAllByText(/24 agents · 14 sidecars/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/agent-to-agent runtime edges/i)).toBeInTheDocument();
    expect(screen.getByText(/openai-codex\/gpt-5\.4/i)).toBeInTheDocument();
    expect(screen.getByText(/Live Operations/i)).toBeInTheDocument();
    expect(screen.getByText(/project-webapp-team/i)).toBeInTheDocument();
    expect(screen.getByText(/Implement landing page/i)).toBeInTheDocument();
    expect(screen.getByText(/%42/i)).toBeInTheDocument();
    expect(screen.getByText(/Landing page shell is implemented/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/no gateways are configured for any board yet/i),
    ).not.toBeInTheDocument();
  });
});

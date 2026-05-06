import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AgentsPage from "./page";
import { customFetch } from "@/api/mutator";

let mockAgents: unknown[] = [];
let mockGateways: unknown[] = [];

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: () => ({ isAdmin: true }),
}));

vi.mock("@/lib/use-url-sorting", () => ({
  useUrlSorting: () => ({ sorting: [], onSortingChange: vi.fn() }),
}));

vi.mock("@/components/templates/DashboardPageLayout", () => ({
  DashboardPageLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children }: { children: React.ReactNode }) => (
    <button>{children}</button>
  ),
}));

vi.mock("@/components/ui/confirm-action-dialog", () => ({
  ConfirmActionDialog: () => null,
}));

vi.mock("@/components/agents/AgentsTable", () => ({
  AgentsTable: (props: {
    agents?: unknown[];
    emptyState?: { description?: string };
  }) => (
    <div>
      <span data-testid="agent-count">{props.agents?.length ?? 0}</span>
      <span>{props.emptyState?.description}</span>
      {props.agents?.map((agent, index) => {
        const row = agent as { name?: string; status?: string };
        return (
          <span key={`${row.name}:${row.status}:${index}`}>
            {row.name}:{row.status}
          </span>
        );
      })}
    </div>
  ),
}));

vi.mock("@/api/generated/boards/boards", () => ({
  getListBoardsApiV1BoardsGetQueryKey: () => ["boards"],
  useListBoardsApiV1BoardsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/api/generated/agents/agents", () => ({
  getListAgentsApiV1AgentsGetQueryKey: () => ["agents"],
  useListAgentsApiV1AgentsGet: () => ({
    data: { status: 200, data: { items: mockAgents } },
    isLoading: false,
  }),
  useDeleteAgentApiV1AgentsAgentIdDelete: () => ({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

vi.mock("@/api/generated/gateways/gateways", () => ({
  useListGatewaysApiV1GatewaysGet: () => ({
    data: { status: 200, data: { items: mockGateways } },
    isLoading: false,
  }),
}));

vi.mock("@/api/mutator", () => ({
  ApiError: class ApiError extends Error {},
  customFetch: vi.fn(),
}));

vi.mock("@/lib/list-delete", () => ({
  createOptimisticListDeleteMutation: () => ({}),
}));

describe("/agents empty state copy", () => {
  beforeEach(() => {
    mockAgents = [];
    mockGateways = [];
    vi.mocked(customFetch).mockReset();
  });

  it("uses global Mission Control wording instead of board-specific wording", () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <AgentsPage />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(
        /create your first agent to start executing tasks across mission control/i,
      ),
    ).toBeInTheDocument();
  });

  it("includes live gateway runtime agents in the admin roster", async () => {
    mockGateways = [
      {
        id: "gateway-1",
        name: "Local Gateway",
        url: "ws://127.0.0.1:18789",
        token: "gateway-token",
        disable_device_pairing: false,
        allow_insecure_tls: false,
      },
    ];
    mockAgents = [
      {
        id: "agent-db",
        gateway_id: "gateway-1",
        board_id: null,
        name: "Gateway Agent",
        status: "offline",
        openclaw_session_id: "agent:gateway:main",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    vi.mocked(customFetch).mockResolvedValue({
      status: 200,
      headers: new Headers(),
      data: {
        summary: { agents_total: 2, subagents_total: 1 },
        agents: [
          {
            agent_id: "gateway",
            session_key: "agent:gateway:main",
            status: "idle",
            updated_at: Date.parse("2026-01-02T00:00:00Z"),
            model_provider: "openai-codex",
            model: "gpt-5.4",
          },
          {
            agent_id: "ops",
            session_key: "agent:ops:main",
            status: "working",
            updated_at: Date.parse("2026-01-02T00:00:00Z"),
            model_provider: "openai-codex",
            model: "gpt-5.4",
          },
        ],
        subagents: [
          {
            agent_id: "ops",
            session_key: "agent:ops:subagent:1",
            status: "idle",
            updated_at: Date.parse("2026-01-02T00:00:00Z"),
          },
        ],
      },
    });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <AgentsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("agent-count")).toHaveTextContent("3");
    });
    expect(screen.getByText("Gateway Agent:online")).toBeInTheDocument();
    expect(screen.getByText("ops:busy")).toBeInTheDocument();
    expect(screen.getByText("ops:online")).toBeInTheDocument();
  });
});

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import GatewayDetailPage from "./page";

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
    useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
      if (queryKey[0] === "gateway-crons") {
        return { data: { crons: [] }, isLoading: false, error: null };
      }
      if (queryKey[0] === "gateway-runtime-overview") {
        return {
          data: {
            generated_at_ms: 1,
            summary: { agents: 0, subagents: 0, edges: 0 },
            agents: [],
            subagents: [],
            edges: [],
          },
          isLoading: false,
          error: null,
        };
      }
      return { data: undefined, isLoading: false, error: null };
    },
  };
});

vi.mock("@/components/agents/AgentsTable", () => ({
  AgentsTable: ({ emptyMessage }: { emptyMessage?: string }) => <div>{emptyMessage}</div>,
}));

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

vi.mock("@/components/ui/confirm-action-dialog", () => ({
  ConfirmActionDialog: () => null,
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
        workspace_root: "/home/amish/.openclaw",
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
      },
    },
    isLoading: false,
    error: null,
  }),
  useGatewaysStatusApiV1GatewaysStatusGet: () => ({
    data: {
      status: 200,
      data: { connected: true, gateway_url: "ws://127.0.0.1:18789", sessions_count: 0 },
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useListBoardsApiV1BoardsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/api/generated/agents/agents", () => ({
  getListAgentsApiV1AgentsGetQueryKey: () => ["agents"],
  useListAgentsApiV1AgentsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
  useDeleteAgentApiV1AgentsAgentIdDelete: () => ({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

vi.mock("@/lib/list-delete", () => ({
  createOptimisticListDeleteMutation: () => ({}),
}));

describe("/gateways/[gatewayId]", () => {
  it("renders precise empty states for runtime edges, agents, and cron jobs", () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <GatewayDetailPage />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: /local openclaw gateway/i })).toBeInTheDocument();
    expect(screen.getByText(/no collaboration edges detected from current sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/no agents assigned to this gateway/i)).toBeInTheDocument();
    expect(screen.getByText(/no cron jobs reported by this gateway/i)).toBeInTheDocument();
  });
});

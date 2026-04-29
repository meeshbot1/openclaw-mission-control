import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AgentsPage from "./page";

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
  DashboardPageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}));

vi.mock("@/components/ui/confirm-action-dialog", () => ({
  ConfirmActionDialog: () => null,
}));

vi.mock("@/components/agents/AgentsTable", () => ({
  AgentsTable: ({ emptyState }: { emptyState?: { description?: string } }) => (
    <div>{emptyState?.description}</div>
  ),
}));

vi.mock("@/api/generated/boards/boards", () => ({
  getListBoardsApiV1BoardsGetQueryKey: () => ["boards"],
  useListBoardsApiV1BoardsGet: () => ({ data: { status: 200, data: { items: [] } }, isLoading: false }),
}));

vi.mock("@/api/generated/agents/agents", () => ({
  getListAgentsApiV1AgentsGetQueryKey: () => ["agents"],
  useListAgentsApiV1AgentsGet: () => ({ data: { status: 200, data: { items: [] } }, isLoading: false }),
  useDeleteAgentApiV1AgentsAgentIdDelete: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

vi.mock("@/lib/list-delete", () => ({
  createOptimisticListDeleteMutation: () => ({}),
}));

describe("/agents empty state copy", () => {
  it("uses global Mission Control wording instead of board-specific wording", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <AgentsPage />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(/create your first agent to start executing tasks across mission control/i),
    ).toBeInTheDocument();
  });
});

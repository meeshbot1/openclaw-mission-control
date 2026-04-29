import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import GlobalApprovalsPage from "./page";

vi.mock("@/auth/clerk", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: React.ReactNode }) => null,
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/components/organisms/DashboardSidebar", () => ({
  DashboardSidebar: () => <div data-testid="dashboard-sidebar" />,
}));

vi.mock("@/components/templates/DashboardShell", () => ({
  DashboardShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useListBoardsApiV1BoardsGet: () => ({
    data: { status: 200, data: { items: [] } },
    isLoading: false,
  }),
}));

vi.mock("@/components/BoardApprovalsPanel", () => ({
  BoardApprovalsPanel: ({ error, emptyState }: { error?: string | null; emptyState?: { title: string; description: string } }) => (
    <div>
      {error ? <div>{error}</div> : null}
      <div>{emptyState?.title ?? "missing empty title"}</div>
      <div>{emptyState?.description ?? "missing empty description"}</div>
    </div>
  ),
}));

describe("/approvals with no boards", () => {
  it("shows a configuration empty state instead of an all-clear approvals message", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <GlobalApprovalsPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText(/no boards configured yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(/create a board before mission control can collect approvals across workflows/i),
    ).toBeInTheDocument();
  });
});

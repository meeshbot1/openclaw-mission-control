import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import NewAgentPage from "./page";

let boardsQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: () => ({ isAdmin: true }),
}));

vi.mock("@/components/templates/DashboardPageLayout", () => ({
  DashboardPageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock("@/components/ui/searchable-select", () => ({
  default: ({ ariaLabel }: { ariaLabel?: string }) => <div aria-label={ariaLabel}>board select</div>,
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-value={value}>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <div>{placeholder}</div>,
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useListBoardsApiV1BoardsGet: () => boardsQueryState,
}));

vi.mock("@/api/generated/agents/agents", () => ({
  useCreateAgentApiV1AgentsPost: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("/agents/new loading state", () => {
  it("shows a visible board-loading notice before the create form is ready", () => {
    boardsQueryState = { isLoading: true, data: undefined, error: null };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <NewAgentPage />
      </QueryClientProvider>,
    );

    expect(screen.getAllByText("Loading boards…")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Loading boards…" })).toBeDisabled();
  });
});

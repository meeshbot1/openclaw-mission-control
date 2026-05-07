import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import EditAgentPage from "./page";

let boardsQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };
let agentQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ agentId: "agent-123" }),
}));

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
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
  useGetAgentApiV1AgentsAgentIdGet: () => agentQueryState,
  useUpdateAgentApiV1AgentsAgentIdPatch: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("/agents/[agentId]/edit loading state", () => {
  it("shows a visible loading notice while the edit form data is still loading", () => {
    boardsQueryState = { isLoading: true, data: undefined, error: null };
    agentQueryState = { isLoading: true, data: undefined, error: null };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <EditAgentPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Loading agent details…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Loading agent…" })).toBeDisabled();
  });
});

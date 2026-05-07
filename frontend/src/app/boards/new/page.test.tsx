import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import NewBoardPage from "./page";

let gatewaysQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };
let groupsQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
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

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

vi.mock("@/components/ui/searchable-select", () => ({
  default: ({ ariaLabel }: { ariaLabel?: string }) => <div aria-label={ariaLabel}>select</div>,
}));

vi.mock("@/api/generated/gateways/gateways", () => ({
  useListGatewaysApiV1GatewaysGet: () => gatewaysQueryState,
}));

vi.mock("@/api/generated/board-groups/board-groups", () => ({
  useListBoardGroupsApiV1BoardGroupsGet: () => groupsQueryState,
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useCreateBoardApiV1BoardsPost: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("/boards/new loading state", () => {
  it("shows a visible setup-loading notice before board creation options are ready", () => {
    gatewaysQueryState = { isLoading: true, data: undefined, error: null };
    groupsQueryState = { isLoading: true, data: undefined, error: null };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <NewBoardPage />
      </QueryClientProvider>,
    );

    expect(screen.getAllByText("Loading board setup…")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Loading board setup…" })).toBeDisabled();
  });
});

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import EditBoardGroupPage from "./page";

let groupQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null, refetch: vi.fn() };
let allBoardsQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null, refetch: vi.fn() };
let groupBoardsQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null, refetch: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ groupId: "group-123" }),
  useSearchParams: () => ({ get: () => null }),
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

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

vi.mock("@/api/generated/board-groups/board-groups", () => ({
  useGetBoardGroupApiV1BoardGroupsGroupIdGet: () => groupQueryState,
  useUpdateBoardGroupApiV1BoardGroupsGroupIdPatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/api/generated/boards/boards", () => ({
  useListBoardsApiV1BoardsGet: (_params: unknown, options?: { query?: unknown }) => {
    const enabled = Boolean((options as { query?: { enabled?: boolean } } | undefined)?.query?.enabled);
    return enabled && _params && typeof _params === "object" && "board_group_id" in (_params as Record<string, unknown>)
      ? groupBoardsQueryState
      : allBoardsQueryState;
  },
  updateBoardApiV1BoardsBoardIdPatch: vi.fn(),
}));

describe("/board-groups/[groupId]/edit loading state", () => {
  it("shows a visible setup-loading notice while group details and boards are loading", () => {
    groupQueryState = { isLoading: true, data: undefined, error: null, refetch: vi.fn() };
    allBoardsQueryState = { isLoading: true, data: undefined, error: null, refetch: vi.fn() };
    groupBoardsQueryState = { isLoading: true, data: undefined, error: null, refetch: vi.fn() };

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <EditBoardGroupPage />
      </QueryClientProvider>,
    );

    expect(screen.getAllByText("Loading group setup…")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Loading group setup…" })).toBeDisabled();
  });
});

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import SettingsPage from "./page";

let meQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
  useUser: () => ({
    user: {
      fullName: "Ada Lovelace",
      primaryEmailAddress: { emailAddress: "ada@example.com" },
    },
  }),
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
  default: ({ ariaLabel, disabled }: { ariaLabel?: string; disabled?: boolean }) => (
    <div aria-label={ariaLabel} data-disabled={disabled ? "true" : "false"}>timezone select</div>
  ),
}));

vi.mock("@/components/ui/confirm-action-dialog", () => ({
  ConfirmActionDialog: () => null,
}));

vi.mock("@/api/generated/users/users", () => ({
  getGetMeApiV1UsersMeGetQueryKey: () => ["me"],
  useGetMeApiV1UsersMeGet: () => meQueryState,
  useUpdateMeApiV1UsersMePatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteMeApiV1UsersMeDelete: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("/settings loading state", () => {
  it("shows a visible profile-loading notice while the profile query is pending", () => {
    meQueryState = { isLoading: true, data: undefined, error: null };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Loading your profile…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Loading profile…" })).toBeDisabled();
  });
});

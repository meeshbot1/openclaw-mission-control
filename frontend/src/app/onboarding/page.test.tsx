import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import OnboardingPage from "./page";

let meQueryState = { isLoading: false, data: undefined as unknown, error: null as { message?: string } | null };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/auth/clerk", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: React.ReactNode }) => null,
  SignInButton: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => ({ isSignedIn: true }),
  useUser: () => ({ user: { fullName: "Ada Lovelace" } }),
}));

vi.mock("@/components/templates/DashboardShell", () => ({
  DashboardShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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
  default: ({ ariaLabel }: { ariaLabel?: string }) => <div aria-label={ariaLabel}>timezone select</div>,
}));

vi.mock("@/lib/onboarding", () => ({
  isOnboardingComplete: () => false,
}));

vi.mock("@/api/generated/users/users", () => ({
  useGetMeApiV1UsersMeGet: () => meQueryState,
  useUpdateMeApiV1UsersMePatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("/onboarding loading state", () => {
  it("shows a visible profile-loading notice while onboarding data loads", () => {
    meQueryState = { isLoading: true, data: undefined, error: null };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <OnboardingPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Loading your profile…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Loading profile…" })).toBeDisabled();
  });
});

import type React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { GlobalLoader } from "./global-loader";

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function PendingQuery() {
  useQuery({
    queryKey: ["pending-loader-test"],
    queryFn: () => new Promise(() => undefined),
  });

  return null;
}

describe("GlobalLoader", () => {
  it("stays hidden when no API work is active", () => {
    renderWithClient(<GlobalLoader />);

    expect(screen.getByRole("status", { hidden: true })).toHaveAttribute(
      "data-state",
      "hidden",
    );
  });

  it("becomes visible while React Query is fetching", async () => {
    renderWithClient(
      <>
        <GlobalLoader />
        <PendingQuery />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveAttribute("data-state", "visible");
    });
  });
});

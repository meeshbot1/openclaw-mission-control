import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import ActivityPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => {
  type LinkProps = React.PropsWithChildren<{
    href: string | { pathname?: string };
  }> &
    Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

  return {
    default: ({ href, children, ...props }: LinkProps) => (
      <a href={typeof href === "string" ? href : "#"} {...props}>
        {children}
      </a>
    ),
  };
});

vi.mock("@/auth/clerk", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: () => null,
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/components/organisms/DashboardSidebar", () => ({
  DashboardSidebar: () => <div data-testid="dashboard-sidebar" />,
}));

vi.mock("@/components/templates/DashboardShell", () => ({
  DashboardShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/auth/SignedOutPanel", () => ({
  SignedOutPanel: ({ message }: { message: string }) => <div>{message}</div>,
}));

vi.mock("@/components/atoms/Markdown", () => ({
  Markdown: ({ content }: { content: string }) => <span>{content}</span>,
}));

vi.mock("@/hooks/usePageActive", () => ({
  usePageActive: () => true,
}));

vi.mock("@/api/generated/organizations/organizations", () => ({
  useGetMyMembershipApiV1OrganizationsMeMemberGet: () => ({
    data: { status: 200, data: { role: "member", user_id: "user-1" } },
  }),
}));

vi.mock("@/api/generated/boards/boards", () => ({
  listBoardsApiV1BoardsGet: vi.fn().mockResolvedValue({
    status: 200,
    data: { items: [] },
  }),
  getBoardSnapshotApiV1BoardsBoardIdSnapshotGet: vi.fn(),
}));

vi.mock("@/api/generated/activity/activity", () => ({
  listActivityApiV1ActivityGet: vi.fn().mockResolvedValue({
    status: 200,
    data: { items: [] },
  }),
}));

vi.mock("@/api/generated/agents/agents", () => ({
  streamAgentsApiV1AgentsStreamGet: vi.fn(),
}));

vi.mock("@/api/generated/approvals/approvals", () => ({
  streamApprovalsApiV1BoardsBoardIdApprovalsStreamGet: vi.fn(),
}));

vi.mock("@/api/generated/board-memory/board-memory", () => ({
  streamBoardMemoryApiV1BoardsBoardIdMemoryStreamGet: vi.fn(),
}));

vi.mock("@/api/generated/tasks/tasks", () => ({
  streamTasksApiV1BoardsBoardIdTasksStreamGet: vi.fn(),
}));

describe("/activity empty state", () => {
  it("shows a configuration-specific message when no boards exist", async () => {
    render(<ActivityPage />);

    await waitFor(() => {
      expect(screen.getByText(/no boards configured yet/i)).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        /create a board before mission control can collect live task, approval, agent, and chat activity/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/waiting for new activity/i)).not.toBeInTheDocument();
  });
});

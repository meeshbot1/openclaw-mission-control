export const DASHBOARD_DETAIL_CARD_META = {
  "online-agents": {
    title: "Online Agents",
    description: "Runtime agent, sidecar, and worker availability across connected gateways.",
  },
  "tasks-in-progress": {
    title: "Tasks In Progress",
    description: "Active work-in-flight counts across dashboard metrics and live OMX teams.",
  },
  "error-rate": {
    title: "Error Rate",
    description: "Recent delivery risk, failed work, and activity signals from the dashboard.",
  },
  "completion-speed": {
    title: "Completion Speed",
    description: "Throughput and completion consistency across the last seven days.",
  },
  workload: {
    title: "Workload",
    description: "Current task distribution across inbox, active, review, and completed work.",
  },
  throughput: {
    title: "Throughput",
    description: "Recent task completion velocity, review pressure, and error trend context.",
  },
  "gateway-health": {
    title: "Gateway Health",
    description: "Gateway connectivity, runtime issues, and unlinked board coverage.",
  },
  "agents-and-teams": {
    title: "Agents and Teams",
    description: "Runtime agent and sidecar coverage collected from connected gateways.",
  },
  "collaboration-graph": {
    title: "Collaboration Graph",
    description: "Agent-to-agent runtime edges and active model coverage.",
  },
  "cron-jobs": {
    title: "Cron Jobs",
    description: "Gateway cron coverage, enabled jobs, and failing last-run signals.",
  },
  "boards-tasks-feeds": {
    title: "Boards, Tasks, Feeds",
    description: "Board coverage, tracked tasks, and recent activity feed availability.",
  },
  "codex-teams": {
    title: "Codex Teams",
    description: "Live OMX team coordination status and tracked task counts.",
  },
  "worker-panes": {
    title: "Worker Panes",
    description: "Worker pane availability, activity state, and task ownership snapshots.",
  },
  "runtime-gateways": {
    title: "Runtime Gateways",
    description: "Gateway runtime response coverage surfaced by live operations scans.",
  },
  "codex-threads": {
    title: "Codex Threads",
    description: "Tracked Codex session attachments, thread activity, and runtime freshness.",
  },
  "scan-roots": {
    title: "Scan Roots",
    description: "Workspace roots scanned for live mission-control telemetry.",
  },
} as const;

export type DashboardDetailCardId = keyof typeof DASHBOARD_DETAIL_CARD_META;

export const dashboardDetailHref = (cardId: DashboardDetailCardId): string =>
  `/dashboard/details/${cardId}`;

export const isDashboardDetailCardId = (value: string): value is DashboardDetailCardId =>
  value in DASHBOARD_DETAIL_CARD_META;

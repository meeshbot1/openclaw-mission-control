"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  AgentsTable,
  type AgentTableRow,
} from "@/components/agents/AgentsTable";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";

import { ApiError, customFetch } from "@/api/mutator";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useDeleteAgentApiV1AgentsAgentIdDelete,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import {
  type listBoardsApiV1BoardsGetResponse,
  getListBoardsApiV1BoardsGetQueryKey,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import { type AgentRead } from "@/api/generated/model";
import { createOptimisticListDeleteMutation } from "@/lib/list-delete";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { useUrlSorting } from "@/lib/use-url-sorting";

const AGENT_SORTABLE_COLUMNS = [
  "name",
  "status",
  "model_provider",
  "model_name",
  "openclaw_session_id",
  "board_id",
  "last_seen_at",
  "updated_at",
];

type GatewayTarget = {
  gatewayId: string;
  gatewayName: string;
  gatewayUrl: string;
  gatewayToken: string | null;
  disableDevicePairing: boolean;
  allowInsecureTls: boolean;
};

type GatewayRuntimeSessionStatus = {
  agent_id: string;
  session_key: string;
  status: string;
  raw_status?: string | null;
  updated_at?: number | null;
  channel?: string | null;
  model_provider?: string | null;
  model?: string | null;
  working_on?: string | null;
  with_agents?: string[];
  is_subagent?: boolean;
  label?: string | null;
};

type GatewayRuntimeOverview = {
  summary: Record<string, number>;
  agents: GatewayRuntimeSessionStatus[];
  subagents: GatewayRuntimeSessionStatus[];
};

type GatewayRuntimeSnapshot = GatewayTarget & {
  overview: GatewayRuntimeOverview | null;
  requestError: string | null;
};

const gatewayQueryParams = (target: GatewayTarget): URLSearchParams => {
  const params = new URLSearchParams();
  params.set("gateway_url", target.gatewayUrl);
  params.set(
    "gateway_disable_device_pairing",
    String(target.disableDevicePairing),
  );
  params.set("gateway_allow_insecure_tls", String(target.allowInsecureTls));
  return params;
};

const runtimeStatusToAgentStatus = (
  status: string | null | undefined,
): string => {
  const normalized = (status ?? "").trim().toLowerCase();
  if (["working", "busy", "in_progress"].includes(normalized)) return "busy";
  if (["idle", "done", "waiting", "online"].includes(normalized))
    return "online";
  if (["broken", "error", "failed", "offline"].includes(normalized))
    return "offline";
  return normalized || "online";
};

const runtimeTimestamp = (updatedAt: number | null | undefined): string => {
  if (typeof updatedAt !== "number" || !Number.isFinite(updatedAt)) {
    return new Date().toISOString();
  }
  const date = new Date(updatedAt);
  return Number.isNaN(date.getTime())
    ? new Date().toISOString()
    : date.toISOString();
};

const runtimeRowName = (session: GatewayRuntimeSessionStatus): string =>
  session.agent_id?.trim() ||
  session.label?.trim() ||
  session.working_on?.trim() ||
  session.session_key;

const runtimeSessionToAgent = (
  session: GatewayRuntimeSessionStatus,
  target: GatewayTarget,
  kind: "agent" | "subagent",
): AgentTableRow => {
  const timestamp = runtimeTimestamp(session.updated_at);
  return {
    id: `runtime:${target.gatewayId}:${session.session_key}`,
    gateway_id: target.gatewayId,
    board_id: null,
    name: runtimeRowName(session),
    status: runtimeStatusToAgentStatus(session.status),
    model_provider: session.model_provider ?? "openai-codex",
    model_name: session.model ?? null,
    openclaw_session_id: session.session_key,
    last_seen_at: timestamp,
    created_at: timestamp,
    updated_at: timestamp,
    runtime_only: true,
    runtime_kind: kind,
    runtime_gateway_name: target.gatewayName,
  };
};

const mergeRuntimeAgents = (
  provisionedAgents: AgentRead[],
  runtimeSnapshots: GatewayRuntimeSnapshot[],
): AgentTableRow[] => {
  const rowsBySession = new Map<string, AgentTableRow>();
  const remainingProvisioned = new Set(
    provisionedAgents.map((agent) => agent.id),
  );

  for (const agent of provisionedAgents) {
    if (agent.openclaw_session_id) {
      rowsBySession.set(agent.openclaw_session_id, { ...agent });
    }
  }

  for (const snapshot of runtimeSnapshots) {
    if (!snapshot.overview) continue;
    const runtimeRows = [
      ...snapshot.overview.agents.map((session) =>
        runtimeSessionToAgent(session, snapshot, "agent"),
      ),
      ...snapshot.overview.subagents.map((session) =>
        runtimeSessionToAgent(session, snapshot, "subagent"),
      ),
    ];
    for (const runtimeRow of runtimeRows) {
      const sessionKey = runtimeRow.openclaw_session_id;
      if (!sessionKey) continue;
      const existing = rowsBySession.has(sessionKey)
        ? rowsBySession.get(sessionKey)
        : null;
      if (existing) {
        rowsBySession.set(sessionKey, {
          ...existing,
          status: runtimeRow.status,
          model_provider: runtimeRow.model_provider,
          model_name: runtimeRow.model_name,
          last_seen_at: runtimeRow.last_seen_at,
          updated_at: runtimeRow.updated_at,
          runtime_gateway_name: runtimeRow.runtime_gateway_name,
        });
        remainingProvisioned.delete(existing.id);
        continue;
      }
      rowsBySession.set(sessionKey, runtimeRow);
    }
  }

  return [
    ...Array.from(rowsBySession.values()),
    ...provisionedAgents
      .filter((agent) => remainingProvisioned.has(agent.id))
      .map((agent) => ({ ...agent })),
  ];
};

export default function AgentsPage() {
  const { isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();

  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const { sorting, onSortingChange } = useUrlSorting({
    allowedColumnIds: AGENT_SORTABLE_COLUMNS,
    defaultSorting: [{ id: "name", desc: false }],
    paramPrefix: "agents",
  });

  const [deleteTarget, setDeleteTarget] = useState<AgentRead | null>(null);

  const boardsKey = getListBoardsApiV1BoardsGetQueryKey();
  const agentsKey = getListAgentsApiV1AgentsGetQueryKey();

  const boardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 30_000,
      refetchOnMount: "always",
    },
  });

  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 15_000,
      refetchOnMount: "always",
    },
  });

  const gatewaysQuery = useListGatewaysApiV1GatewaysGet<
    listGatewaysApiV1GatewaysGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 30_000,
      refetchOnMount: "always",
    },
  });

  const boards = useMemo(
    () =>
      boardsQuery.data?.status === 200
        ? (boardsQuery.data.data.items ?? [])
        : [],
    [boardsQuery.data],
  );
  const provisionedAgents = useMemo(
    () =>
      agentsQuery.data?.status === 200
        ? (agentsQuery.data.data.items ?? [])
        : [],
    [agentsQuery.data],
  );
  const gatewayTargets = useMemo<GatewayTarget[]>(
    () =>
      gatewaysQuery.data?.status === 200
        ? (gatewaysQuery.data.data.items ?? []).map((gateway) => ({
            gatewayId: gateway.id,
            gatewayName: gateway.name,
            gatewayUrl: gateway.url,
            gatewayToken: gateway.token ?? null,
            disableDevicePairing: Boolean(gateway.disable_device_pairing),
            allowInsecureTls: Boolean(gateway.allow_insecure_tls),
          }))
        : [],
    [gatewaysQuery.data],
  );
  const gatewayRuntimeQuery = useQuery<GatewayRuntimeSnapshot[], ApiError>({
    queryKey: [
      "agents",
      "gateway-runtime-overviews",
      gatewayTargets.map(
        (target) => `${target.gatewayId}:${target.gatewayUrl}`,
      ),
    ],
    enabled: Boolean(isSignedIn && isAdmin && gatewayTargets.length > 0),
    refetchInterval: 15_000,
    refetchOnMount: "always",
    queryFn: async ({ signal }) => {
      return Promise.all(
        gatewayTargets.map(async (target): Promise<GatewayRuntimeSnapshot> => {
          try {
            const params = gatewayQueryParams(target);
            const response = await customFetch<{
              data: GatewayRuntimeOverview;
              status: number;
              headers: Headers;
            }>(`/api/v1/gateways/runtime-overview?${params.toString()}`, {
              method: "GET",
              signal,
            });
            return {
              ...target,
              overview: response.status === 200 ? response.data : null,
              requestError:
                response.status === 200
                  ? null
                  : `Runtime overview request failed (${response.status})`,
            };
          } catch (error) {
            if (signal.aborted) throw error;
            return {
              ...target,
              overview: null,
              requestError:
                error instanceof Error
                  ? error.message
                  : "Runtime overview request failed.",
            };
          }
        }),
      );
    },
  });
  const agents = useMemo(
    () =>
      mergeRuntimeAgents(
        provisionedAgents,
        gatewayRuntimeQuery.data ?? [],
      ).sort((a, b) => a.name.localeCompare(b.name)),
    [gatewayRuntimeQuery.data, provisionedAgents],
  );
  const runtimeAgentCount = useMemo(
    () =>
      (gatewayRuntimeQuery.data ?? []).reduce((total, snapshot) => {
        const overview = snapshot.overview;
        return (
          total +
          (overview?.agents.length ?? 0) +
          (overview?.subagents.length ?? 0)
        );
      }, 0),
    [gatewayRuntimeQuery.data],
  );

  const deleteMutation = useDeleteAgentApiV1AgentsAgentIdDelete<
    ApiError,
    { previous?: listAgentsApiV1AgentsGetResponse }
  >(
    {
      mutation: createOptimisticListDeleteMutation<
        AgentRead,
        listAgentsApiV1AgentsGetResponse,
        { agentId: string }
      >({
        queryClient,
        queryKey: agentsKey,
        getItemId: (agent) => agent.id,
        getDeleteId: ({ agentId }) => agentId,
        onSuccess: () => {
          setDeleteTarget(null);
        },
        invalidateQueryKeys: [agentsKey, boardsKey],
      }),
    },
    queryClient,
  );

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate({ agentId: deleteTarget.id });
  };

  return (
    <>
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view agents.",
          forceRedirectUrl: "/agents",
          signUpForceRedirectUrl: "/agents",
        }}
        title="Agents"
        description={`${agents.length} visible agent${agents.length === 1 ? "" : "s"} (${runtimeAgentCount} live runtime, ${provisionedAgents.length} provisioned).`}
        headerActions={
          agents.length > 0 ? (
            <Button onClick={() => router.push("/agents/new")}>
              New agent
            </Button>
          ) : null
        }
        isAdmin={isAdmin}
        adminOnlyMessage="Only organization owners and admins can access agents."
        stickyHeader
      >
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <AgentsTable
            agents={agents}
            boards={boards}
            isLoading={
              agentsQuery.isLoading ||
              gatewaysQuery.isLoading ||
              gatewayRuntimeQuery.isLoading
            }
            isRefreshing={
              (agentsQuery.isFetching || gatewaysQuery.isFetching || gatewayRuntimeQuery.isFetching) &&
              !(agentsQuery.isLoading || gatewaysQuery.isLoading || gatewayRuntimeQuery.isLoading)
            }
            sorting={sorting}
            onSortingChange={onSortingChange}
            showActions
            stickyHeader
            onDelete={setDeleteTarget}
            emptyState={{
              title: "No agents yet",
              description:
                "Create your first agent to start executing tasks across Mission Control.",
              actionHref: "/agents/new",
              actionLabel: "Create your first agent",
            }}
          />
        </div>

        {agentsQuery.error ? (
          <p className="mt-4 text-sm text-red-500">
            {agentsQuery.error.message}
          </p>
        ) : null}
        {gatewayRuntimeQuery.error ? (
          <p className="mt-4 text-sm text-red-500">
            {gatewayRuntimeQuery.error.message}
          </p>
        ) : null}
      </DashboardPageLayout>

      <ConfirmActionDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        ariaLabel="Delete agent"
        title="Delete agent"
        description={
          <>
            This will remove {deleteTarget?.name}. This action cannot be undone.
          </>
        }
        errorMessage={deleteMutation.error?.message}
        onConfirm={handleDelete}
        isConfirming={deleteMutation.isPending}
      />
    </>
  );
}

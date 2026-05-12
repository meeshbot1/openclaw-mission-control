"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AgentsTable } from "@/components/agents/AgentsTable";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";

import { ApiError, customFetch } from "@/api/mutator";
import {
  type listBoardsApiV1BoardsGetResponse,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import {
  type gatewaysStatusApiV1GatewaysStatusGetResponse,
  type getGatewayApiV1GatewaysGatewayIdGetResponse,
  useGatewaysStatusApiV1GatewaysStatusGet,
  useGetGatewayApiV1GatewaysGatewayIdGet,
} from "@/api/generated/gateways/gateways";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useDeleteAgentApiV1AgentsAgentIdDelete,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import { type AgentRead } from "@/api/generated/model";
import { formatTimestamp } from "@/lib/formatters";
import { toGatewayCronView } from "@/lib/gateway-crons";
import { createOptimisticListDeleteMutation } from "@/lib/list-delete";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

const maskToken = (value?: string | null) => {
  if (!value) return "—";
  if (value.length <= 8) return "••••";
  return `••••${value.slice(-4)}`;
};

type GatewayRuntimeSessionStatus = {
  agent_id: string;
  session_key: string;
  status: string;
  raw_status?: string | null;
  updated_at?: number | null;
  age_seconds?: number | null;
  channel?: string | null;
  model_provider?: string | null;
  model?: string | null;
  working_on?: string | null;
  with_agents: string[];
  is_subagent: boolean;
  parent_agent_id?: string | null;
  parent_session_key?: string | null;
  label?: string | null;
};

type GatewayRuntimeEdge = {
  from_agent: string;
  to_agent: string;
  relation: string;
  session_key?: string | null;
};

type GatewayRuntimeOverview = {
  generated_at_ms: number;
  summary: Record<string, number>;
  agents: GatewayRuntimeSessionStatus[];
  subagents: GatewayRuntimeSessionStatus[];
  edges: GatewayRuntimeEdge[];
};

type GatewaySessionHistory = {
  history: unknown[];
};

const gatewayQueryString = (
  statusParams: {
    gateway_url?: string;
    gateway_disable_device_pairing?: boolean;
    gateway_allow_insecure_tls?: boolean;
  },
): string => {
  const params = new URLSearchParams();
  if (statusParams.gateway_url) {
    params.set("gateway_url", statusParams.gateway_url);
  }
  if (typeof statusParams.gateway_disable_device_pairing === "boolean") {
    params.set(
      "gateway_disable_device_pairing",
      String(statusParams.gateway_disable_device_pairing),
    );
  }
  if (typeof statusParams.gateway_allow_insecure_tls === "boolean") {
    params.set(
      "gateway_allow_insecure_tls",
      String(statusParams.gateway_allow_insecure_tls),
    );
  }
  return params.toString();
};

const runtimeStatusClass = (status: string | null | undefined) => {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "working") return "bg-amber-100 text-amber-800";
  if (normalized === "waiting") return "bg-sky-100 text-sky-800";
  if (normalized === "broken") return "bg-rose-100 text-rose-800";
  if (normalized === "idle") return "bg-emerald-100 text-emerald-800";
  return "bg-slate-100 text-slate-700";
};

export default function GatewayDetailPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useParams();
  const { isSignedIn } = useAuth();
  const gatewayIdParam = params?.gatewayId;
  const gatewayId = Array.isArray(gatewayIdParam)
    ? gatewayIdParam[0]
    : gatewayIdParam;

  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const [deleteTarget, setDeleteTarget] = useState<AgentRead | null>(null);
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(null);
  const agentsKey = getListAgentsApiV1AgentsGetQueryKey(
    gatewayId ? { gateway_id: gatewayId } : undefined,
  );

  const gatewayQuery = useGetGatewayApiV1GatewaysGatewayIdGet<
    getGatewayApiV1GatewaysGatewayIdGetResponse,
    ApiError
  >(gatewayId ?? "", {
    query: {
      enabled: Boolean(isSignedIn && isAdmin && gatewayId),
      refetchInterval: 30_000,
    },
  });

  const gateway =
    gatewayQuery.data?.status === 200 ? gatewayQuery.data.data : null;

  const boardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 30_000,
    },
  });

  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
    ApiError
  >(gatewayId ? { gateway_id: gatewayId } : undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin && gatewayId),
      refetchInterval: 15_000,
    },
  });
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
        invalidateQueryKeys: [agentsKey],
      }),
    },
    queryClient,
  );

  const statusParams = gateway
    ? {
        gateway_url: gateway.url,
        gateway_disable_device_pairing: gateway.disable_device_pairing,
        gateway_allow_insecure_tls: gateway.allow_insecure_tls,
      }
    : {};

  const statusQuery = useGatewaysStatusApiV1GatewaysStatusGet<
    gatewaysStatusApiV1GatewaysStatusGetResponse,
    ApiError
  >(statusParams, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin && gateway),
      refetchInterval: 15_000,
    },
  });

  const agents = useMemo(
    () =>
      agentsQuery.data?.status === 200
        ? (agentsQuery.data.data.items ?? [])
        : [],
    [agentsQuery.data],
  );
  const boards = useMemo(
    () =>
      boardsQuery.data?.status === 200
        ? (boardsQuery.data.data.items ?? [])
        : [],
    [boardsQuery.data],
  );

  const status =
    statusQuery.data?.status === 200 ? statusQuery.data.data : null;
  const isConnected = status?.connected ?? false;
  const gatewayRuntimeQueryString = gatewayQueryString(statusParams);
  const cronQuery = useQuery<{ crons: object[] }, ApiError>({
    queryKey: [
      "gateway-crons",
      gatewayId,
      statusParams.gateway_url,
      statusParams.gateway_disable_device_pairing,
      statusParams.gateway_allow_insecure_tls,
    ],
    enabled: Boolean(isSignedIn && isAdmin && gateway),
    refetchInterval: 30_000,
    queryFn: async () => {
      const response = await customFetch<{
        data: { crons: object[] };
        status: number;
        headers: Headers;
      }>(`/api/v1/gateways/crons?${gatewayRuntimeQueryString}`, {
        method: "GET",
      });
      return response.data;
    },
  });
  const cronRecords = useMemo(
    () => (cronQuery.data?.crons ?? []).map((item) => toGatewayCronView(item)),
    [cronQuery.data?.crons],
  );
  const runtimeQuery = useQuery<GatewayRuntimeOverview, ApiError>({
    queryKey: [
      "gateway-runtime-overview",
      gatewayId,
      statusParams.gateway_url,
      statusParams.gateway_disable_device_pairing,
      statusParams.gateway_allow_insecure_tls,
    ],
    enabled: Boolean(isSignedIn && isAdmin && gateway),
    refetchInterval: 15_000,
    queryFn: async () => {
      const response = await customFetch<{
        data: GatewayRuntimeOverview;
        status: number;
        headers: Headers;
      }>(`/api/v1/gateways/runtime-overview?${gatewayRuntimeQueryString}`, {
        method: "GET",
      });
      return response.data;
    },
  });
  const sessionHistoryQuery = useQuery<GatewaySessionHistory, ApiError>({
    queryKey: [
      "gateway-session-history",
      gatewayId,
      selectedSessionKey,
      gatewayRuntimeQueryString,
    ],
    enabled: Boolean(isSignedIn && isAdmin && gateway && selectedSessionKey),
    refetchInterval: 5_000,
    queryFn: async () => {
      const response = await customFetch<{
        data: GatewaySessionHistory;
        status: number;
        headers: Headers;
      }>(
        `/api/v1/gateways/sessions/${encodeURIComponent(
          selectedSessionKey ?? "",
        )}/history?${gatewayRuntimeQueryString}`,
        { method: "GET" },
      );
      return response.data;
    },
  });
  const runtimeAgents = useMemo(
    () =>
      [...(runtimeQuery.data?.agents ?? [])].sort(
        (left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0),
      ),
    [runtimeQuery.data?.agents],
  );
  const runtimeSubagents = useMemo(
    () =>
      [...(runtimeQuery.data?.subagents ?? [])].sort(
        (left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0),
      ),
    [runtimeQuery.data?.subagents],
  );

  const title = gateway?.name ? gateway.name : "Gateway";
  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate({ agentId: deleteTarget.id });
  };

  return (
    <>
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view a gateway.",
          forceRedirectUrl: `/gateways/${gatewayId}`,
        }}
        title={title}
        description="Gateway configuration and connection details."
        headerActions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => router.push("/gateways")}>
              Back to gateways
            </Button>
            {isAdmin && gatewayId ? (
              <Button
                onClick={() => router.push(`/gateways/${gatewayId}/edit`)}
              >
                Edit gateway
              </Button>
            ) : null}
          </div>
        }
        isAdmin={isAdmin}
        adminOnlyMessage="Only organization owners and admins can access gateways."
      >
        {gatewayQuery.isLoading ? (
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
            Loading gateway…
          </div>
        ) : gatewayQuery.error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
            {gatewayQuery.error.message}
          </div>
        ) : gateway ? (
          <div className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Connection
                  </p>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        statusQuery.isLoading
                          ? "bg-slate-300"
                          : isConnected
                            ? "bg-emerald-500"
                            : "bg-rose-500"
                      }`}
                    />
                    <span>
                      {statusQuery.isLoading
                        ? "Checking"
                        : isConnected
                          ? "Online"
                          : "Offline"}
                    </span>
                  </div>
                </div>
                <div className="mt-4 space-y-3 text-sm text-slate-700">
                  <div>
                    <p className="text-xs uppercase text-slate-400">
                      Gateway URL
                    </p>
                    <p className="mt-1 text-sm font-medium text-slate-900">
                      {gateway.url}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-400">Token</p>
                    <p className="mt-1 text-sm font-medium text-slate-900">
                      {maskToken(gateway.token)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-slate-400">
                      Device pairing
                    </p>
                    <p className="mt-1 text-sm font-medium text-slate-900">
                      {gateway.disable_device_pairing ? "Disabled" : "Required"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Runtime
                </p>
                <div className="mt-4 space-y-3 text-sm text-slate-700">
                  <div>
                    <p className="text-xs uppercase text-slate-400">
                      Workspace root
                    </p>
                    <p className="mt-1 text-sm font-medium text-slate-900">
                      {gateway.workspace_root}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase text-slate-400">
                        Created
                      </p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {formatTimestamp(gateway.created_at)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-slate-400">
                        Updated
                      </p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {formatTimestamp(gateway.updated_at)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Runtime map
                </p>
                <span className="text-xs text-slate-500">
                  {runtimeQuery.isLoading
                    ? "Loading…"
                    : `${runtimeAgents.length} agents · ${runtimeSubagents.length} subagents`}
                </span>
              </div>
              {runtimeQuery.error ? (
                <p className="mt-4 text-sm text-rose-600">
                  {runtimeQuery.error.message}
                </p>
              ) : (
                <>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {Object.entries(runtimeQuery.data?.summary ?? {}).map(
                      ([key, value]) => (
                        <span
                          key={key}
                          className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                        >
                          {key.replaceAll("_", " ")}: {value}
                        </span>
                      ),
                    )}
                  </div>

                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm text-slate-700">
                      <thead className="text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2">Agent</th>
                          <th className="px-3 py-2">Status</th>
                          <th className="px-3 py-2">Working on</th>
                          <th className="px-3 py-2">With</th>
                          <th className="px-3 py-2">Updated</th>
                          <th className="px-3 py-2">Logs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runtimeAgents.map((item) => (
                          <tr
                            key={item.session_key}
                            className="border-t border-slate-100"
                          >
                            <td className="px-3 py-2 font-medium text-slate-900">
                              {item.agent_id}
                            </td>
                            <td className="px-3 py-2">
                              <span
                                className={`rounded-full px-2 py-1 text-xs font-medium ${runtimeStatusClass(
                                  item.status,
                                )}`}
                              >
                                {item.status}
                              </span>
                            </td>
                            <td className="max-w-[24rem] truncate px-3 py-2 text-slate-700">
                              {item.working_on ?? item.session_key}
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              {item.with_agents.length
                                ? item.with_agents.join(", ")
                                : "—"}
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              {item.updated_at
                                ? formatTimestamp(
                                    new Date(item.updated_at).toISOString(),
                                  )
                                : "—"}
                            </td>
                            <td className="px-3 py-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setSelectedSessionKey(item.session_key)}
                              >
                                View logs
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="mt-6">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Recent subagents
                    </p>
                    {runtimeSubagents.length === 0 ? (
                      <p className="mt-2 text-sm text-slate-500">
                        No subagent sessions found.
                      </p>
                    ) : (
                      <div className="mt-2 overflow-x-auto">
                        <table className="min-w-full text-left text-sm text-slate-700">
                          <thead className="text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-3 py-2">Subagent</th>
                              <th className="px-3 py-2">Parent</th>
                              <th className="px-3 py-2">Status</th>
                              <th className="px-3 py-2">Task</th>
                              <th className="px-3 py-2">Logs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {runtimeSubagents.slice(0, 20).map((item) => (
                              <tr
                                key={item.session_key}
                                className="border-t border-slate-100"
                              >
                                <td className="px-3 py-2 font-medium text-slate-900">
                                  {item.agent_id}
                                </td>
                                <td className="px-3 py-2 text-slate-600">
                                  {item.parent_agent_id ?? "—"}
                                </td>
                                <td className="px-3 py-2">
                                  <span
                                    className={`rounded-full px-2 py-1 text-xs font-medium ${runtimeStatusClass(
                                      item.status,
                                    )}`}
                                  >
                                    {item.status}
                                  </span>
                                </td>
                                <td className="max-w-[24rem] truncate px-3 py-2 text-slate-700">
                                  {item.label ?? item.working_on ?? "—"}
                                </td>
                                <td className="px-3 py-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setSelectedSessionKey(item.session_key)}
                                  >
                                    View logs
                                  </Button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="mt-6">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Collaboration edges
                    </p>
                    {runtimeQuery.data?.edges.length ? (
                      <div className="mt-2 overflow-x-auto">
                        <table className="min-w-full text-left text-sm text-slate-700">
                          <thead className="text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-3 py-2">From</th>
                              <th className="px-3 py-2">Relation</th>
                              <th className="px-3 py-2">To</th>
                              <th className="px-3 py-2">Session</th>
                            </tr>
                          </thead>
                          <tbody>
                            {runtimeQuery.data.edges.slice(0, 30).map((edge) => (
                              <tr
                                key={`${edge.from_agent}:${edge.to_agent}:${edge.relation}:${edge.session_key ?? ""}`}
                                className="border-t border-slate-100"
                              >
                                <td className="px-3 py-2 font-medium text-slate-900">
                                  {edge.from_agent}
                                </td>
                                <td className="px-3 py-2 text-slate-600">
                                  {edge.relation.replaceAll("_", " ")}
                                </td>
                                <td className="px-3 py-2 font-medium text-slate-900">
                                  {edge.to_agent}
                                </td>
                                <td className="max-w-[20rem] truncate px-3 py-2 text-slate-600">
                                  {edge.session_key ?? "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="mt-2 text-sm text-slate-500">
                        No collaboration edges detected from current sessions.
                      </p>
                    )}
                  </div>

                  {selectedSessionKey ? (
                    <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Realtime session logs
                          </p>
                          <p className="mt-1 break-all font-mono text-xs text-slate-700">
                            {selectedSessionKey}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-500">
                            {sessionHistoryQuery.isFetching
                              ? "Refreshing…"
                              : "Auto-refresh 5s"}
                          </span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelectedSessionKey(null)}
                          >
                            Close
                          </Button>
                        </div>
                      </div>
                      {sessionHistoryQuery.error ? (
                        <p className="mt-3 text-sm text-rose-600">
                          {sessionHistoryQuery.error.message}
                        </p>
                      ) : sessionHistoryQuery.isLoading ? (
                        <p className="mt-3 text-sm text-slate-500">
                          Loading session history…
                        </p>
                      ) : sessionHistoryQuery.data?.history.length ? (
                        <div className="mt-3 max-h-96 space-y-2 overflow-y-auto">
                          {sessionHistoryQuery.data.history.map((entry, index) => (
                            <pre
                              key={`${selectedSessionKey}:${index}`}
                              className="whitespace-pre-wrap break-words rounded-md bg-white p-3 text-xs text-slate-700"
                            >
                              {JSON.stringify(entry, null, 2)}
                            </pre>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-3 text-sm text-slate-500">
                          No chat history was returned for this runtime session.
                        </p>
                      )}
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Agents
                </p>
                {agentsQuery.isLoading ? (
                  <span className="text-xs text-slate-500">Loading…</span>
                ) : (
                  <span className="text-xs text-slate-500">
                    {agents.length} total
                  </span>
                )}
              </div>
              <div className="mt-4">
                <AgentsTable
                  agents={agents}
                  boards={boards}
                  isLoading={agentsQuery.isLoading}
                  isRefreshing={agentsQuery.isFetching && !agentsQuery.isLoading}
                  onDelete={setDeleteTarget}
                  emptyMessage="No agents assigned to this gateway."
                />
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Cron jobs
                </p>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">
                    {cronQuery.isLoading
                      ? "Loading…"
                      : `${cronRecords.length} configured`}
                  </span>
                  {gatewayId ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => router.push(`/gateways/${gatewayId}/crons`)}
                    >
                      View cron dashboard
                    </Button>
                  ) : null}
                </div>
              </div>
              {cronQuery.error ? (
                <p className="mt-4 text-sm text-rose-600">
                  {cronQuery.error.message}
                </p>
              ) : cronRecords.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">
                  No cron jobs reported by this gateway.
                </p>
              ) : (
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm text-slate-700">
                    <thead className="text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-3 py-2">Name</th>
                        <th className="px-3 py-2">What it does</th>
                        <th className="px-3 py-2">Schedule</th>
                        <th className="px-3 py-2">Enabled</th>
                        <th className="px-3 py-2">Last run</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2">Target</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cronRecords.map((cron) => (
                        <tr key={cron.id} className="border-t border-slate-100">
                          <td className="px-3 py-2 font-medium text-slate-900">
                            {cron.name}
                          </td>
                          <td className="max-w-[28rem] truncate px-3 py-2 text-slate-600">
                            {cron.purpose}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs text-slate-700">
                            {cron.timezone
                              ? `${cron.schedule} (${cron.timezone})`
                              : cron.schedule}
                          </td>
                          <td className="px-3 py-2">{cron.enabledLabel}</td>
                          <td className="px-3 py-2 text-slate-600">
                            {cron.lastRunAtMs
                              ? formatTimestamp(
                                  new Date(cron.lastRunAtMs).toISOString(),
                                )
                              : "—"}
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {cron.model ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {cron.target}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
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

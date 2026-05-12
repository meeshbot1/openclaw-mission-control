"use client";

export const dynamic = "force-dynamic";

import { Fragment, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { useQuery } from "@tanstack/react-query";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";

import { ApiError, customFetch } from "@/api/mutator";
import {
  type getGatewayApiV1GatewaysGatewayIdGetResponse,
  useGetGatewayApiV1GatewaysGatewayIdGet,
} from "@/api/generated/gateways/gateways";
import { formatTimestamp } from "@/lib/formatters";
import { toGatewayCronView } from "@/lib/gateway-crons";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

const statusPillClass = (value: string | null) => {
  const normalized = (value ?? "").toLowerCase();
  if (normalized === "ok" || normalized === "done") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (normalized === "failed" || normalized === "error" || normalized === "timeout") {
    return "bg-rose-100 text-rose-800";
  }
  if (normalized === "running") {
    return "bg-amber-100 text-amber-800";
  }
  return "bg-slate-100 text-slate-700";
};

const formatMs = (value: number | null): string => {
  if (!value) return "—";
  return formatTimestamp(new Date(value).toISOString());
};

export default function GatewayCronDashboardPage() {
  const router = useRouter();
  const params = useParams();
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const [selectedCronId, setSelectedCronId] = useState<string | null>(null);

  const gatewayIdParam = params?.gatewayId;
  const gatewayId = Array.isArray(gatewayIdParam)
    ? gatewayIdParam[0]
    : gatewayIdParam;

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

  const statusParams = gateway
    ? {
        gateway_url: gateway.url,
        gateway_disable_device_pairing: gateway.disable_device_pairing,
        gateway_allow_insecure_tls: gateway.allow_insecure_tls,
      }
    : {};

  const cronQuery = useQuery<{ crons: object[] }, ApiError>({
    queryKey: [
      "gateway-crons-dashboard",
      gatewayId,
      statusParams.gateway_url,
      statusParams.gateway_disable_device_pairing,
      statusParams.gateway_allow_insecure_tls,
    ],
    enabled: Boolean(isSignedIn && isAdmin && gateway),
    refetchInterval: 15_000,
    queryFn: async () => {
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
      const response = await customFetch<{
        data: { crons: object[] };
        status: number;
        headers: Headers;
      }>(`/api/v1/gateways/crons?${params.toString()}`, {
        method: "GET",
      });
      return response.data;
    },
  });

  const cronRecords = useMemo(
    () => (cronQuery.data?.crons ?? []).map((item) => toGatewayCronView(item)),
    [cronQuery.data?.crons],
  );
  const enabledCount = cronRecords.filter((item) => item.enabled === true).length;
  const disabledCount = cronRecords.filter((item) => item.enabled === false).length;
  const failingCount = cronRecords.filter((item) => {
    const status = (item.lastRunStatus ?? "").toLowerCase();
    return status === "failed" || status === "error" || status === "timeout";
  }).length;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view cron jobs.",
        forceRedirectUrl: gatewayId ? `/gateways/${gatewayId}/crons` : "/gateways",
      }}
      title={gateway?.name ? `${gateway.name} cron dashboard` : "Cron dashboard"}
      description="Gateway cron schedule, health, execution metadata, and model routing."
      headerActions={
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => router.push("/gateways")}>
            Back to gateways
          </Button>
          {gatewayId ? (
            <Button
              variant="outline"
              onClick={() => router.push(`/gateways/${gatewayId}`)}
            >
              Back to gateway
            </Button>
          ) : null}
        </div>
      }
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can access gateway cron jobs."
    >
      {gatewayQuery.isLoading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
          Loading gateway…
        </div>
      ) : gatewayQuery.error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
          {gatewayQuery.error.message}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase text-slate-500">Total jobs</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">
                {cronRecords.length}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase text-slate-500">Enabled</p>
              <p className="mt-1 text-xl font-semibold text-emerald-700">
                {enabledCount}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase text-slate-500">Disabled</p>
              <p className="mt-1 text-xl font-semibold text-slate-700">
                {disabledCount}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase text-slate-500">Failing last run</p>
              <p className="mt-1 text-xl font-semibold text-rose-700">
                {failingCount}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Cron jobs
              </p>
              <span className="text-xs text-slate-500">
                {cronQuery.isLoading ? "Loading…" : "Auto-refresh 15s"}
              </span>
            </div>
            {cronQuery.error ? (
              <p className="mt-4 text-sm text-rose-600">{cronQuery.error.message}</p>
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
                      <th className="px-3 py-2">Agent</th>
                      <th className="px-3 py-2">Model</th>
                      <th className="px-3 py-2">Last run</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Next run</th>
                      <th className="px-3 py-2">Target</th>
                      <th className="px-3 py-2">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cronRecords.map((cron) => (
                      <Fragment key={cron.id}>
                        <tr className="border-t border-slate-100">
                          <td className="px-3 py-2 font-medium text-slate-900">
                            {cron.name}
                          </td>
                          <td className="max-w-[26rem] truncate px-3 py-2 text-slate-600">
                            {cron.purpose}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs text-slate-700">
                            {cron.timezone
                              ? `${cron.schedule} (${cron.timezone})`
                              : cron.schedule}
                          </td>
                          <td className="px-3 py-2">{cron.enabledLabel}</td>
                          <td className="px-3 py-2 text-slate-600">
                            {cron.agentId ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {cron.model ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {formatMs(cron.lastRunAtMs)}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`rounded-full px-2 py-1 text-xs font-medium ${statusPillClass(
                                cron.lastRunStatus,
                              )}`}
                            >
                              {cron.lastRunStatus ?? "—"}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {formatMs(cron.nextRunAtMs)}
                          </td>
                          <td className="max-w-[20rem] truncate px-3 py-2 text-slate-600">
                            {cron.target}
                          </td>
                          <td className="px-3 py-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                setSelectedCronId(
                                  selectedCronId === cron.id ? null : cron.id,
                                )
                              }
                            >
                              {selectedCronId === cron.id ? "Hide" : "Inspect"}
                            </Button>
                          </td>
                        </tr>
                        {selectedCronId === cron.id ? (
                          <tr className="border-t border-slate-100 bg-slate-50">
                            <td colSpan={11} className="px-3 py-3">
                              <div className="grid gap-3 text-sm text-slate-700 md:grid-cols-3">
                                <div>
                                  <p className="text-xs uppercase text-slate-500">
                                    Schedule
                                  </p>
                                  <p className="mt-1 font-mono text-xs">
                                    {cron.timezone
                                      ? `${cron.schedule} (${cron.timezone})`
                                      : cron.schedule}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-xs uppercase text-slate-500">
                                    Last run log
                                  </p>
                                  <p className="mt-1">
                                    {cron.lastRunStatus ?? "No status"} ·{" "}
                                    {formatMs(cron.lastRunAtMs)}
                                    {cron.lastDurationMs
                                      ? ` · ${cron.lastDurationMs}ms`
                                      : ""}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-xs uppercase text-slate-500">
                                    Runtime target
                                  </p>
                                  <p className="mt-1 break-all font-mono text-xs">
                                    {cron.target}
                                  </p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardPageLayout>
  );
}

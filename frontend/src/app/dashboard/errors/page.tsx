"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bot, CalendarClock, Database, RefreshCcw } from "lucide-react";

import { SignedIn, SignedOut, useAuth } from "@/auth/clerk";
import { ApiError, customFetch } from "@/api/mutator";
import { SignedOutPanel } from "@/components/auth/SignedOutPanel";
import { DashboardSidebar } from "@/components/organisms/DashboardSidebar";
import { DashboardShell } from "@/components/templates/DashboardShell";
import { Button } from "@/components/ui/button";
import { formatRelativeTimestamp, formatTimestamp } from "@/lib/formatters";

type ErrorRegistryItem = {
  id: number;
  source_kind: string;
  source: string;
  event_ts: string;
  level: string;
  service?: string | null;
  category?: string | null;
  fix_type?: string | null;
  message: string;
  status: string;
  fix_attempts: number;
  last_seen_at: string;
  last_fix_attempt_at?: string | null;
  fixed_at?: string | null;
  assigned_agent_id?: string | null;
  assigned_cron_id?: string | null;
  assigned_cron_name?: string | null;
  assigned_cron_schedule?: string | null;
  assigned_cron_timezone?: string | null;
  assigned_cron_enabled?: boolean | null;
  assigned_cron_next_run_at_ms?: number | null;
  assigned_cron_last_run_at_ms?: number | null;
  assigned_cron_last_run_status?: string | null;
  remediation_schedule_status: string;
  assignment_state: string;
  assignment_reason?: string | null;
  action_items: string[];
};

type ErrorRegistryResponse = {
  db_path?: string | null;
  generated_at: string;
  summary: {
    total: number;
    open: number;
    observed: number;
    ignored: number;
    fixed: number;
    assigned: number;
    working: number;
  };
  items: ErrorRegistryItem[];
};

const statusOptions = [
  { value: "open", label: "Open" },
  { value: "observed", label: "Observed" },
  { value: "ignored", label: "Ignored" },
  { value: "all", label: "All" },
] as const;

const levelClass = (level: string): string => {
  const normalized = level.toLowerCase();
  if (normalized === "fatal" || normalized === "error") {
    return "bg-rose-100 text-rose-700";
  }
  if (normalized === "warning" || normalized === "warn") {
    return "bg-amber-100 text-amber-700";
  }
  return "bg-slate-200 text-slate-700";
};

const statusClass = (status: string): string => {
  const normalized = status.toLowerCase();
  if (normalized === "open") return "bg-rose-100 text-rose-700";
  if (normalized === "observed") return "bg-blue-100 text-blue-700";
  if (normalized === "ignored") return "bg-slate-200 text-slate-700";
  if (normalized === "fixed") return "bg-emerald-100 text-emerald-700";
  return "bg-slate-200 text-slate-700";
};

const formatEventTime = (value: string): string => {
  try {
    return formatTimestamp(value);
  } catch {
    return value || "—";
  }
};

const formatEpochMs = (value?: number | null): string => {
  if (!value) return "—";
  return formatTimestamp(new Date(value).toISOString());
};

const scheduledFixPrimary = (item: ErrorRegistryItem): string => {
  if (item.assigned_cron_next_run_at_ms) {
    return `Next ${formatEpochMs(item.assigned_cron_next_run_at_ms)}`;
  }
  if (item.remediation_schedule_status === "running") {
    return "Running now";
  }
  if (item.assigned_cron_enabled === false) {
    return "Not scheduled";
  }
  if (item.assigned_cron_schedule) {
    return "Schedule pending";
  }
  return "No cron scheduled";
};

const scheduledFixSecondary = (item: ErrorRegistryItem): string => {
  const owner = item.assigned_cron_name ?? item.assigned_agent_id ?? "No owner";
  if (item.assigned_cron_enabled === false) {
    return `${owner} is disabled`;
  }
  const schedule =
    item.assigned_cron_schedule ?? item.remediation_schedule_status;
  const timezone = item.assigned_cron_timezone
    ? ` · ${item.assigned_cron_timezone}`
    : "";
  return `${owner} · ${schedule}${timezone}`;
};

const shortSource = (value: string): string => {
  const normalized = value.replace(
    /^\/home\/amish\/\.openclaw\//,
    "~/.openclaw/",
  );
  return normalized.length > 90 ? `...${normalized.slice(-87)}` : normalized;
};

export default function DashboardErrorsPage() {
  const { isSignedIn } = useAuth();
  const [statusFilter, setStatusFilter] =
    useState<(typeof statusOptions)[number]["value"]>("open");

  const errorsQuery = useQuery<ErrorRegistryResponse, ApiError>({
    queryKey: ["dashboard", "mission-control-error-registry", statusFilter],
    enabled: Boolean(isSignedIn),
    refetchInterval: 30_000,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        status: statusFilter,
        limit: "200",
      });
      const response = await customFetch<{
        data: ErrorRegistryResponse;
        status: number;
        headers: Headers;
      }>(`/api/v1/gateways/mission-control/errors?${params.toString()}`, {
        method: "GET",
        signal,
      });
      if (response.status !== 200) {
        throw new Error(`Error registry request failed (${response.status})`);
      }
      return response.data;
    },
  });

  const data = errorsQuery.data ?? null;
  const summaryCards = useMemo(
    () => [
      { label: "Rows", value: data?.summary.total ?? 0 },
      { label: "Assigned", value: data?.summary.assigned ?? 0 },
      { label: "Working", value: data?.summary.working ?? 0 },
      { label: "Open", value: data?.summary.open ?? 0 },
    ],
    [data],
  );

  return (
    <DashboardShell>
      <SignedOut>
        <SignedOutPanel
          message="Sign in to view logged errors."
          forceRedirectUrl="/dashboard/errors"
        />
      </SignedOut>
      <SignedIn>
        <DashboardSidebar />
        <main className="flex-1 overflow-y-auto bg-slate-50">
          <div className="space-y-4 p-4 md:p-8">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Database className="h-5 w-5 text-slate-500" />
                    <h1 className="text-2xl font-semibold text-slate-900">
                      Logged Errors
                    </h1>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">
                    {data?.db_path
                      ? shortSource(data.db_path)
                      : "Error registry unavailable"}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {statusOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setStatusFilter(option.value)}
                      className={`rounded-md border px-3 py-1.5 text-sm font-medium transition ${
                        statusFilter === option.value
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                  <Button
                    variant="outline"
                    onClick={() => {
                      void errorsQuery.refetch();
                    }}
                    disabled={errorsQuery.isFetching}
                  >
                    <RefreshCcw
                      className={`mr-2 h-4 w-4 ${errorsQuery.isFetching ? "animate-spin" : ""}`}
                    />
                    Refresh
                  </Button>
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {summaryCards.map((card) => (
                  <div
                    key={card.label}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                  >
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {card.label}
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-900">
                      {card.value.toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {errorsQuery.error ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                {errorsQuery.error.message}
              </div>
            ) : errorsQuery.isLoading ? (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
                Loading logged errors...
              </div>
            ) : !data?.items.length ? (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
                No logged errors match this filter.
              </div>
            ) : (
              <div className="space-y-3">
                {data.items.map((item) => (
                  <section
                    key={item.id}
                    className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                  >
                    <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${levelClass(
                              item.level,
                            )}`}
                          >
                            {item.level}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(
                              item.status,
                            )}`}
                          >
                            {item.status}
                          </span>
                          {item.category ? (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                              {item.category}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-2 line-clamp-2 text-sm font-medium text-slate-900">
                          {item.message}
                        </p>
                        <p className="mt-2 truncate font-mono text-xs text-slate-500">
                          {shortSource(item.source)}
                        </p>
                      </div>

                      <div className="grid shrink-0 gap-2 text-sm text-slate-600 sm:grid-cols-2 xl:min-w-[42rem] xl:grid-cols-3">
                        <div className="rounded-lg bg-slate-50 p-3">
                          <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            <Bot className="h-3.5 w-3.5" />
                            Assigned
                          </p>
                          <p className="mt-1 font-medium text-slate-900">
                            {item.assigned_agent_id ?? "Unassigned"}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {item.assigned_cron_name ??
                              item.assignment_reason ??
                              "No cron"}
                          </p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-3">
                          <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            <CalendarClock className="h-3.5 w-3.5" />
                            Activity
                          </p>
                          <p className="mt-1 font-medium text-slate-900">
                            {item.assignment_state}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {item.last_seen_at
                              ? formatRelativeTimestamp(item.last_seen_at)
                              : formatEventTime(item.event_ts)}
                          </p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-3 sm:col-span-2 xl:col-span-1">
                          <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            <CalendarClock className="h-3.5 w-3.5" />
                            Scheduled fix
                          </p>
                          <p className="mt-1 font-medium text-slate-900">
                            {scheduledFixPrimary(item)}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {scheduledFixSecondary(item)}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_18rem]">
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Action items
                        </p>
                        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                          {item.action_items.map((action) => (
                            <li key={`${item.id}:${action}`}>{action}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                        <p>
                          <span className="font-medium text-slate-700">
                            First seen:
                          </span>{" "}
                          {formatEventTime(item.event_ts)}
                        </p>
                        <p className="mt-1">
                          <span className="font-medium text-slate-700">
                            Fix attempts:
                          </span>{" "}
                          {item.fix_attempts}
                        </p>
                        {item.assigned_cron_id ? (
                          <p className="mt-1 truncate">
                            <span className="font-medium text-slate-700">
                              Cron:
                            </span>{" "}
                            {item.assigned_cron_id}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </section>
                ))}
              </div>
            )}

            <Link
              href="/dashboard"
              className="inline-flex text-sm font-medium text-slate-600 transition hover:text-slate-900"
            >
              Back to dashboard
            </Link>
          </div>
        </main>
      </SignedIn>
    </DashboardShell>
  );
}

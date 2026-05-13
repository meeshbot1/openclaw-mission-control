"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowUpRight } from "lucide-react";

import { SignedIn, SignedOut } from "@/auth/clerk";
import { SignedOutPanel } from "@/components/auth/SignedOutPanel";
import { DashboardSidebar } from "@/components/organisms/DashboardSidebar";
import { DashboardShell } from "@/components/templates/DashboardShell";
import {
  DASHBOARD_DETAIL_CARD_META,
  isDashboardDetailCardId,
  type DashboardDetailCardId,
} from "@/app/dashboard/detail-links";

const relatedLinks: Partial<
  Record<DashboardDetailCardId, Array<{ href: string; label: string }>>
> = {
  "online-agents": [{ href: "/agents", label: "Open agents" }],
  "tasks-in-progress": [{ href: "/boards", label: "Open boards" }],
  "error-rate": [{ href: "/dashboard/errors", label: "Open logged errors" }],
  "completion-speed": [{ href: "/activity", label: "Open activity" }],
  workload: [{ href: "/boards", label: "Open boards" }],
  throughput: [{ href: "/activity", label: "Open activity" }],
  "gateway-health": [{ href: "/gateways", label: "Open gateways" }],
  "agents-and-teams": [{ href: "/agents", label: "Open agents" }],
  "collaboration-graph": [
    { href: "/dashboard", label: "Open runtime coverage" },
  ],
  "cron-jobs": [{ href: "/gateways", label: "Open gateways" }],
  "boards-tasks-feeds": [{ href: "/boards", label: "Open boards" }],
  "codex-teams": [{ href: "/dashboard", label: "Open live operations" }],
  "worker-panes": [{ href: "/dashboard", label: "Open live operations" }],
  "runtime-gateways": [{ href: "/gateways", label: "Open gateways" }],
  "codex-threads": [{ href: "/dashboard", label: "Open live operations" }],
  "scan-roots": [{ href: "/dashboard", label: "Open live operations" }],
};

export default function DashboardDetailPage() {
  const params = useParams();
  const rawCardId = Array.isArray(params?.cardId)
    ? params.cardId[0]
    : params?.cardId;
  const cardId =
    typeof rawCardId === "string" && isDashboardDetailCardId(rawCardId)
      ? rawCardId
      : null;
  const meta = cardId ? DASHBOARD_DETAIL_CARD_META[cardId] : null;
  const links = cardId ? (relatedLinks[cardId] ?? []) : [];

  return (
    <DashboardShell>
      <SignedOut>
        <SignedOutPanel
          message="Sign in to view dashboard details."
          forceRedirectUrl={
            cardId ? `/dashboard/details/${cardId}` : "/dashboard"
          }
        />
      </SignedOut>
      <SignedIn>
        <DashboardSidebar />
        <main className="flex-1 overflow-y-auto bg-slate-50">
          <div className="p-4 md:p-8">
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:p-6">
              {meta ? (
                <>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Dashboard detail
                      </p>
                      <h1 className="mt-2 text-2xl font-semibold text-slate-900">
                        {meta.title}
                      </h1>
                      <p className="mt-2 max-w-3xl text-sm text-slate-600">
                        {meta.description}
                      </p>
                    </div>
                    <Link
                      href="/dashboard"
                      className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    >
                      Dashboard
                      <ArrowUpRight className="h-4 w-4" />
                    </Link>
                  </div>
                  {links.length ? (
                    <div className="mt-5 flex flex-wrap gap-2">
                      {links.map((link) => (
                        <Link
                          key={`${cardId}:${link.href}`}
                          href={link.href}
                          className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
                        >
                          {link.label}
                          <ArrowUpRight className="h-4 w-4" />
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
                <>
                  <h1 className="text-2xl font-semibold text-slate-900">
                    Dashboard detail not found
                  </h1>
                  <p className="mt-2 text-sm text-slate-600">
                    This dashboard card is not registered.
                  </p>
                  <Link
                    href="/dashboard"
                    className="mt-5 inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
                  >
                    Back to dashboard
                  </Link>
                </>
              )}
            </section>
          </div>
        </main>
      </SignedIn>
    </DashboardShell>
  );
}

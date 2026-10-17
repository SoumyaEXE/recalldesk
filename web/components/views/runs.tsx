"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { RiCalendarScheduleLine, RiCheckboxCircleLine, RiExternalLinkLine, RiNodeTree, RiRefreshLine, RiRestartLine, RiTimerLine } from "@remixicon/react";
import { Button, ButtonLink } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { StepTimeline } from "@/components/rd/step-timeline";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Drawer } from "@/components/ui/overlay";
import { Card, DemoBadge, EmptyState, Eyebrow, IconTile, Pill } from "@/components/ui/surface";
import { DataTable, FilterPill, RowTitle, SearchField, Toolbar, type Column } from "@/components/ui/table";
import { getRuns, isSimulated } from "@/lib/api";
import { durationMs, formatDate, formatDuration, relativeTime, stepFlag, stepLabel } from "@/lib/format";
import type { WorkflowRun } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

const TEMPORAL_UI = "http://localhost:8233";

type Run = WorkflowRun & { note?: string; summary?: { do_not_sell?: number; check_label?: number; items_checked?: number; applied_memories?: number } };

function runFlags(run: WorkflowRun) {
  const flags = run.steps.map(stepFlag);
  return { retries: run.retries ?? run.steps.filter((s) => s.attempt > 1).length, resumed: !!run.resumed_after_crash || flags.includes("resumed") };
}

function StatusPill({ status }: { status: string }) {
  const tone = status === "completed" ? "green" : status === "failed" ? "red" : status === "running" ? "blue" : "gray";
  return (
    <Pill size="sm" tone={tone} dot>
      <span className="capitalize">{status}</span>
    </Pill>
  );
}

function Waterfall({ run }: { run: WorkflowRun }) {
  const starts = run.steps.map((s) => (s.started_at ? new Date(s.started_at).getTime() : NaN)).filter(Number.isFinite);
  const ends = run.steps.map((s) => (s.ended_at ? new Date(s.ended_at).getTime() : NaN)).filter(Number.isFinite);
  if (!starts.length) return <p className="text-body-2-regular text-text-tertiary">No step timings recorded for this run.</p>;
  const t0 = Math.min(...starts);
  const span = Math.max(Math.max(...ends, ...starts) + 1 - t0, 1);
  return (
    <div className="flex flex-col gap-2" role="img" aria-label="Step waterfall">
      {run.steps.map((s, i) => {
        const a = s.started_at ? new Date(s.started_at).getTime() : t0;
        const b = s.ended_at ? new Date(s.ended_at).getTime() : a;
        const left = ((a - t0) / span) * 100;
        const width = Math.max(1.2, ((b - a) / span) * 100);
        const flag = stepFlag(s);
        return (
          <div key={i} className="grid grid-cols-[120px_minmax(0,1fr)_56px] items-center gap-3 sm:grid-cols-[170px_minmax(0,1fr)_64px]">
            <span className="truncate text-caption-1-medium text-text-secondary">{stepLabel(s.name).label}</span>
            <span className="relative h-5 rounded-md bg-subtle ring-1 ring-line ring-inset">
              <span
                className={cx(
                  "absolute inset-y-0.5 rounded",
                  s.status === "failed" ? "bg-stop-solid" : flag === "retried" ? "bg-caution-solid" : flag === "resumed" ? "bg-chart-4" : s.status === "completed" ? "bg-accent-500" : "bg-accent-300",
                )}
                style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                title={`${s.name}: ${formatDuration(durationMs(s.started_at, s.ended_at))}${s.attempt > 1 ? ` · attempt ${s.attempt}` : ""}`}
              />
            </span>
            <span className="text-end text-caption-1-regular text-text-tertiary tabular-nums">{formatDuration(durationMs(s.started_at, s.ended_at))}</span>
          </div>
        );
      })}
      <div className="grid grid-cols-[120px_minmax(0,1fr)_56px] gap-3 sm:grid-cols-[170px_minmax(0,1fr)_64px]">
        <span />
        <span className="flex justify-between text-caption-2-regular text-text-tertiary tabular-nums">
          <span>0s</span>
          <span>{formatDuration(span)}</span>
        </span>
        <span />
      </div>
      <p className="mt-1 flex flex-wrap gap-3 text-caption-2-regular text-text-tertiary" aria-hidden>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-accent-500" /> done
        </span>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-caution-solid" /> retried
        </span>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-chart-4" /> resumed after crash
        </span>
      </p>
    </div>
  );
}

function RunDrawer({ run: current, onClose }: { run: Run | null; onClose: () => void }) {
  const [kept, setKept] = useState(current);
  if (current && current !== kept) setKept(current);
  const run = current ?? kept;
  const f = run ? runFlags(run) : null;
  return (
    <Drawer
      isOpen={!!current}
      onOpenChange={(o) => !o && onClose()}
      width="lg"
      leading={<IconTile icon={run?.workflow_type === "WeeklyRecallSweep" ? RiCalendarScheduleLine : RiNodeTree} tone={f?.resumed ? "violet" : "blue"} />}
      title={run?.workflow_type ?? "Workflow"}
      subtitle={
        run && (
          <span className="flex flex-wrap items-center gap-2">
            <span className="rd-mono break-all text-text-secondary">{run.workflow_id}</span>
          </span>
        )
      }
      footer={
        run &&
        !isSimulated(run.workflow_id) && (
          <ButtonLink href={`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(run.workflow_id)}`} target="_blank" rel="noreferrer" size="small" trailingIcon={RiExternalLinkLine}>
            Open in Temporal UI
          </ButtonLink>
        )
      }
    >
      {run && f && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={run.status} />
            {f.retries > 0 && (
              <Pill size="sm" tone="amber" icon={RiRefreshLine}>
                {f.retries} retr{f.retries === 1 ? "y" : "ies"}
              </Pill>
            )}
            {f.resumed && (
              <Pill size="sm" tone="violet" icon={RiRestartLine}>
                Resumed after crash
              </Pill>
            )}
            {isSimulated(run.workflow_id) && <DemoBadge>Simulated in browser</DemoBadge>}
            {run.placeholder && <DemoBadge>Demo run</DemoBadge>}
          </div>

          {f.resumed && (
            <div className="flex items-start gap-3 rounded-xl border border-line bg-subtle p-4">
              <IconTile icon={RiRestartLine} tone="violet" size="sm" />
              <div className="min-w-0">
                <p className="text-body-2-semibold text-text-primary">Worker killed mid-run, resumed on a fresh worker</p>
                <p className="text-caption-1-regular break-words text-text-secondary">
                  Temporal replayed the event history on the new worker and carried on. Completed activities did not run twice.
                  {run.workers?.length ? (
                    <>
                      {" "}
                      Workers: <span className="rd-mono text-text-primary">{run.workers.join(" → ")}</span>
                    </>
                  ) : null}
                </p>
              </div>
            </div>
          )}

          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
            {[
              { k: "Started", v: formatDate(run.started_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" }) },
              { k: "Duration", v: formatDuration(durationMs(run.started_at, run.ended_at)) },
              { k: "Activities", v: String(run.steps.length || "—") },
              { k: "History events", v: run.history_events != null ? String(run.history_events) : "—" },
              { k: "Shop", v: run.shop_id ?? "all watched" },
              { k: "Card", v: run.card_id ?? "—" },
            ].map((x) => (
              <div key={x.k} className="flex min-w-0 flex-col gap-0.5 bg-card px-4 py-3">
                <dt className="text-caption-1-medium text-text-tertiary">{x.k}</dt>
                <dd className="truncate text-body-2-semibold text-text-primary tabular-nums" title={x.v}>
                  {x.v}
                </dd>
              </div>
            ))}
          </dl>

          {run.summary && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Items checked", run.summary.items_checked, "text-text-primary"],
                ["Do not sell", run.summary.do_not_sell, "text-stop-text"],
                ["Check label", run.summary.check_label, "text-caution-text"],
                ["Memories applied", run.summary.applied_memories, "text-info-text"],
              ].map(([k, v, c]) => (
                <div key={k as string} className="rounded-xl border border-line px-3 py-2.5">
                  <p className="text-caption-1-medium text-text-tertiary">{k as string}</p>
                  <p className={cx("text-title-2-semibold tabular-nums", c as string)}>{v ?? "—"}</p>
                </div>
              ))}
            </div>
          )}

          <section className="flex flex-col gap-3">
            <Eyebrow>Waterfall</Eyebrow>
            <Waterfall run={run} />
          </section>
          <section className="flex flex-col gap-3">
            <Eyebrow>Activity timeline</Eyebrow>
            {run.steps.length ? <StepTimeline steps={run.steps} /> : <p className="text-body-2-regular text-text-tertiary">{run.note ?? "Step progress isn't recorded for this run."} The full event history is in the Temporal UI.</p>}
          </section>
        </div>
      )}
    </Drawer>
  );
}

export function RunsView() {
  const { data, loading, reload, placeholder } = useLoad(getRuns, "runs");
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const openId = params.get("open");
  const [q, setQ] = useState("");
  const [type, setType] = useState("all");
  const runs = useMemo(() => [...((data ?? []) as Run[])].sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? "")), [data]);
  const filtered = runs.filter((r) => (type === "all" || r.workflow_type === type) && (!q.trim() || `${r.workflow_id} ${r.shop_id ?? ""}`.toLowerCase().includes(q.trim().toLowerCase())));
  const selected = openId ? (runs.find((r) => r.workflow_id === openId) ?? null) : null;
  const setOpen = (id: string | null) => {
    const sp = new URLSearchParams(params.toString());
    if (id) sp.set("open", id);
    else sp.delete("open");
    router.replace(`${pathname}${sp.size ? `?${sp}` : ""}`, { scroll: false });
  };

  const totals = useMemo(() => {
    const t = { runs: runs.length, completed: 0, retries: 0, resumed: 0 };
    runs.forEach((r) => {
      const f = runFlags(r);
      if (r.status === "completed") t.completed++;
      t.retries += f.retries;
      if (f.resumed) t.resumed++;
    });
    return t;
  }, [runs]);
  const types = [...new Set(runs.map((r) => r.workflow_type).filter(Boolean) as string[])];

  const columns: Column<Run>[] = [
    {
      id: "wf",
      header: "Workflow",
      mobile: "primary",
      width: "36%",
      sort: (r) => r.workflow_id,
      cell: (r) => (
        <RowTitle
          leading={<IconTile icon={r.workflow_type === "WeeklyRecallSweep" ? RiCalendarScheduleLine : RiNodeTree} tone={runFlags(r).resumed ? "violet" : "blue"} size="sm" />}
          title={<span className="rd-mono">{r.workflow_id}</span>}
          sub={r.workflow_type}
        />
      ),
    },
    { id: "shop", header: "Shop", mobile: "meta", width: "12%", hideBelow: "lg", sort: (r) => r.shop_id ?? "", cell: (r) => <span className="text-body-2-medium text-text-primary">{r.shop_id ?? "all"}</span> },
    { id: "status", header: "Status", mobile: "badge", width: "12%", sort: (r) => r.status, cell: (r) => <StatusPill status={r.status} /> },
    {
      id: "flags",
      header: "Signals",
      mobile: "badge",
      width: "18%",
      cell: (r) => {
        const f = runFlags(r);
        return (
          <span className="flex flex-wrap gap-1">
            {f.resumed && (
              <Pill size="sm" tone="violet" icon={RiRestartLine}>
                Resumed
              </Pill>
            )}
            {f.retries > 0 && (
              <Pill size="sm" tone="amber" icon={RiRefreshLine}>
                {f.retries} retr{f.retries === 1 ? "y" : "ies"}
              </Pill>
            )}
            {isSimulated(r.workflow_id) && <Pill size="sm">Simulated</Pill>}
            {!f.resumed && !f.retries && !isSimulated(r.workflow_id) && <span className="text-caption-1-regular text-text-tertiary">Clean run</span>}
          </span>
        );
      },
    },
    { id: "started", header: "Started", mobile: "meta", width: "12%", sort: (r) => r.started_at ?? "", cell: (r) => <span className="text-body-2-medium whitespace-nowrap text-text-primary">{relativeTime(r.started_at)}</span> },
    { id: "dur", header: "Duration", mobile: "meta", width: "10%", align: "end", sort: (r) => durationMs(r.started_at, r.ended_at) ?? 0, cell: (r) => <span className="text-body-2-medium text-text-primary tabular-nums">{formatDuration(durationMs(r.started_at, r.ended_at))}</span> },
  ];

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Temporal · WeeklyRecallSweep every Thu 2:00 PM ET
            </Pill>
            <DemoBadge show={placeholder}>Includes demo runs</DemoBadge>
          </>
        }
        title="Workflow runs"
        description="Fetch new recalls, extract specs, re-check each shop, compose one card. Every step is a Temporal activity: retried on bad model output, resumed when a worker dies. Retries and crash-resumes are shown, not hidden."
        actions={
          <>
            <Button variant="secondary" leadingIcon={RiRefreshLine} onClick={reload}>
              Refresh
            </Button>
            <ButtonLink href={TEMPORAL_UI} target="_blank" rel="noreferrer" trailingIcon={RiExternalLinkLine}>
              Temporal UI
            </ButtonLink>
          </>
        }
      />

      <KpiRow className="mb-6">
        <KpiCard index={0} icon={RiNodeTree} tone="blue" label="Runs" value={totals.runs} loading={loading} status="Recorded" caption="Sweeps and on-demand checks" />
        <KpiCard index={1} icon={RiCheckboxCircleLine} tone="green" label="Completed" value={totals.completed} loading={loading} status="Succeeded" caption={totals.runs ? `${Math.round((totals.completed / totals.runs) * 100)}% success` : undefined} />
        <KpiCard index={2} icon={RiTimerLine} tone="amber" label="Activity retries" value={totals.retries} loading={loading} status="Backoff" caption="Invalid JSON, CPSC 5xx" />
        <KpiCard index={3} icon={RiRestartLine} tone="violet" label="Resumed after crash" value={totals.resumed} loading={loading} status="Replayed" caption="No activity ran twice" />
      </KpiRow>

      <Card>
        <Toolbar>
          <SearchField value={q} onChange={setQ} placeholder="Workflow id or shop" label="Search runs" className="md:max-w-[320px] md:flex-1" />
          <div className="flex items-center gap-2">
            <FilterPill label="Type" value={type} onChange={setType} options={[{ value: "all", label: "All" }, ...types.map((t) => ({ value: t, label: t }))]} />
          </div>
        </Toolbar>
        <DataTable
          caption="Workflow runs"
          rows={filtered}
          columns={columns}
          rowKey={(r) => r.workflow_id}
          rowLabel={(r) => `Open run ${r.workflow_id}`}
          onRowOpen={(r) => setOpen(r.workflow_id)}
          selectedKey={openId}
          loading={loading}
          initialSort={{ id: "started", dir: "desc" }}
          empty={
            <EmptyState icon={RiNodeTree} title="No runs yet">
              Run a check from Inventory, or wait for Thursday&apos;s sweep.
            </EmptyState>
          }
        />
      </Card>
      <RunDrawer run={selected} onClose={() => setOpen(null)} />
    </Page>
  );
}

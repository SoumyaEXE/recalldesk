"use client";

import { useMemo, useState } from "react";
import { RiCalendarScheduleLine, RiRefreshLine, RiRestartLine } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader, Panel, Stat } from "@/components/rd/app-shell";
import { PlaceholderNote } from "@/components/rd/data-source-chip";
import { StepTimeline } from "@/components/rd/step-timeline";
import { getRuns, isSimulated } from "@/lib/api";
import { durationMs, formatDate, formatDuration, relativeTime, stepFlag, stepLabel } from "@/lib/format";
import type { WorkflowRun } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

function runFlags(run: WorkflowRun) {
  const flags = run.steps.map(stepFlag);
  return {
    retries: run.retries ?? run.steps.filter((s) => s.attempt > 1).length,
    resumed: !!run.resumed_after_crash || flags.includes("resumed"),
  };
}

function StatusDot({ status }: { status: string }) {
  const tone = status === "completed" ? "bg-accent-600" : status === "failed" ? "bg-stop-solid" : status === "running" ? "rd-pulse bg-accent-500 text-accent-500" : "bg-foreground-icon-quaternary";
  return <span className={cx("relative size-2 shrink-0 rounded-full", tone)} aria-hidden />;
}

function Waterfall({ run }: { run: WorkflowRun }) {
  const starts = run.steps.map((s) => (s.started_at ? new Date(s.started_at).getTime() : NaN)).filter(Number.isFinite);
  const ends = run.steps.map((s) => (s.ended_at ? new Date(s.ended_at).getTime() : NaN)).filter(Number.isFinite);
  if (!starts.length) return <p className="text-body-2-regular text-text-tertiary">Not started yet.</p>;
  const t0 = Math.min(...starts);
  const span = Math.max(Math.max(...ends, ...starts) + 1 - t0, 1);
  return (
    <div className="flex flex-col gap-1.5" role="img" aria-label="Step waterfall">
      {run.steps.map((s, i) => {
        const a = s.started_at ? new Date(s.started_at).getTime() : t0;
        const b = s.ended_at ? new Date(s.ended_at).getTime() : a;
        const left = ((a - t0) / span) * 100;
        const width = Math.max(1.2, ((b - a) / span) * 100);
        const flag = stepFlag(s);
        return (
          <div key={i} className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
            <span className="truncate text-caption-1-medium text-text-secondary">{stepLabel(s.name).label}</span>
            <span className="relative h-4 rounded bg-background-secondary-default">
              <span
                className={cx(
                  "absolute inset-y-0 rounded",
                  s.status === "failed" ? "bg-stop-solid" : flag === "retried" ? "bg-caution-solid" : flag === "resumed" ? "bg-accent-400" : s.status === "completed" ? "bg-accent-600" : "bg-accent-300",
                )}
                style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                title={`${s.name}: ${formatDuration(durationMs(s.started_at, s.ended_at))}${s.attempt > 1 ? ` · attempt ${s.attempt}` : ""}`}
              />
            </span>
          </div>
        );
      })}
      <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
        <span />
        <span className="flex justify-between font-mono text-caption-2-regular text-text-tertiary rd-num">
          <span>0s</span>
          <span>{formatDuration(span)}</span>
        </span>
      </div>
      <p className="mt-1 flex flex-wrap gap-3 text-caption-2-regular text-text-tertiary" aria-hidden>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-accent-600" /> done
        </span>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-caution-solid" /> retried
        </span>
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-sm bg-accent-400" /> resumed after crash
        </span>
      </p>
    </div>
  );
}

export function RunsView() {
  const { data, loading, reload, placeholder } = useLoad(getRuns, "runs");
  const runs = useMemo(() => [...(data ?? [])].sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? "")), [data]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = runs.find((r) => r.workflow_id === selectedId) ?? runs[0];

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

  return (
    <Page wide>
      <PageHeader
        eyebrow="Temporal"
        title="Workflow runs"
        description="WeeklyRecallSweep runs on a Temporal Schedule every Thursday at 2:00 PM ET: fetch new recalls, extract specs, re-check each shop, compose one card. Retries and crash-resumes are shown, not hidden."
        actions={
          <>
            <PlaceholderNote show={placeholder}>Includes demo runs</PlaceholderNote>
            <Button variant="secondary" leadingIcon={RiRefreshLine} onClick={reload}>
              Refresh
            </Button>
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Runs" value={loading ? "…" : totals.runs} />
        <Stat label="Completed" value={loading ? "…" : totals.completed} />
        <Stat label="Activity retries" value={loading ? "…" : totals.retries} tone="caution" />
        <Stat label="Resumed after crash" value={loading ? "…" : totals.resumed} tone="ink" />
      </div>

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="h-[420px] animate-pulse rounded-2xl bg-background-secondary-default" />
          <div className="h-[420px] animate-pulse rounded-2xl bg-background-secondary-default" />
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
          <Panel title="Recent runs" padded={false}>
            <ul className="flex flex-col p-1.5" role="listbox" aria-label="Workflow runs">
              {runs.map((r) => {
                const f = runFlags(r);
                const active = r.workflow_id === selected?.workflow_id;
                return (
                  <li key={r.workflow_id} role="option" aria-selected={active}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(r.workflow_id)}
                      className={cx(
                        "flex w-full cursor-pointer flex-col gap-1.5 rounded-xl px-3 py-2.5 text-start outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                        active ? "bg-background-secondary-default ring-1 ring-border-button-default" : "hover:bg-background-secondary-default/70",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <StatusDot status={r.status} />
                        <span className="min-w-0 flex-1 truncate font-mono text-caption-1-medium text-text-primary">{r.workflow_id}</span>
                      </span>
                      <span className="flex flex-wrap items-center gap-1.5 ps-4">
                        {r.workflow_type && (
                          <span className="inline-flex items-center gap-1 rounded bg-background-tertiary-default px-1 font-mono text-caption-2-medium text-text-secondary">
                            {r.workflow_type === "WeeklyRecallSweep" && <RiCalendarScheduleLine className="size-3" aria-hidden />}
                            {r.workflow_type}
                          </span>
                        )}
                        {f.retries > 0 && (
                          <Chip variant="caption" color="yellow" className="gap-1 py-0">
                            <RiRefreshLine className="size-3" aria-hidden /> {f.retries} retr{f.retries === 1 ? "y" : "ies"}
                          </Chip>
                        )}
                        {f.resumed && (
                          <Chip variant="caption" color="blue" className="gap-1 py-0">
                            <RiRestartLine className="size-3" aria-hidden /> Resumed
                          </Chip>
                        )}
                        {isSimulated(r.workflow_id) && (
                          <Chip variant="caption" color="soft" className="py-0">
                            Simulated
                          </Chip>
                        )}
                        <span className="ms-auto text-caption-1-regular text-text-tertiary">{relativeTime(r.started_at)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
              {!runs.length && <li className="px-3 py-8 text-center text-body-2-regular text-text-tertiary">No runs yet.</li>}
            </ul>
          </Panel>

          {selected && (
            <Panel
              key={selected.workflow_id}
              className="rd-rise"
              title={<span className="font-mono text-body-2-semibold break-all">{selected.workflow_id}</span>}
              description={`${selected.workflow_type ?? "Workflow"} · started ${formatDate(selected.started_at, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })}`}
            >
              <div className="flex flex-col gap-6">
                {runFlags(selected).resumed && (
                  <div className="flex items-start gap-3 rounded-xl border border-accent-300 bg-background-secondary-default px-3 py-2.5">
                    <RiRestartLine className="mt-0.5 size-4 shrink-0 text-ink" aria-hidden />
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <p className="text-body-2-semibold text-text-primary">Resumed after worker crash</p>
                      <p className="text-caption-1-regular break-words text-text-secondary">
                        The worker was killed mid-run. Temporal replayed the event history on a fresh worker and carried on; completed activities did not run twice.
                        {selected.workers?.length ? <span className="font-mono"> {selected.workers.join(" → ")}</span> : null}
                      </p>
                    </div>
                  </div>
                )}
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
                  {[
                    { k: "Status", v: selected.status },
                    { k: "Duration", v: formatDuration(durationMs(selected.started_at, selected.ended_at)) },
                    { k: "Activities", v: String(selected.steps.length) },
                    { k: "Total attempts", v: String(selected.steps.reduce((n, s) => n + Math.max(1, s.attempt), 0)) },
                    ...(selected.history_events != null ? [{ k: "History events", v: String(selected.history_events) }] : []),
                    ...(selected.shop_id ? [{ k: "Shop", v: selected.shop_id }] : selected.workers?.length ? [{ k: "Workers", v: String(selected.workers.length) }] : []),
                  ].map((x) => (
                    <div key={x.k} className="rounded-xl bg-background-secondary-default px-3 py-2">
                      <dt className="text-caption-1-medium text-text-tertiary">{x.k}</dt>
                      <dd className="font-mono text-body-2-semibold break-all text-text-primary capitalize rd-num">{x.v}</dd>
                    </div>
                  ))}
                </dl>
                <section className="flex flex-col gap-3">
                  <h3 className="rd-eyebrow text-text-tertiary">Waterfall</h3>
                  <Waterfall run={selected} />
                </section>
                <section className="flex flex-col gap-3">
                  <h3 className="rd-eyebrow text-text-tertiary">Event timeline</h3>
                  <StepTimeline steps={selected.steps} />
                </section>
              </div>
            </Panel>
          )}
        </div>
      )}
    </Page>
  );
}

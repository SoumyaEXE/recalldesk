import { RiArchiveDrawerLine, RiCheckLine, RiCloseLine, RiRefreshLine, RiRestartLine } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { durationMs, formatDuration, stepFlag, stepLabel } from "@/lib/format";
import type { WorkflowStep } from "@/lib/types";
import { cx } from "@/utils/cx";

function StepIcon({ step }: { step: WorkflowStep }) {
  const base = "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full";
  switch (step.status) {
    case "completed":
      return (
        <span className={cx(base, "bg-accent-600 text-white")}>
          <RiCheckLine className="size-3.5" aria-hidden />
        </span>
      );
    case "failed":
      return (
        <span className={cx(base, "bg-stop-solid text-white")}>
          <RiCloseLine className="size-3.5" aria-hidden />
        </span>
      );
    case "retrying":
      return (
        <span className={cx(base, "border border-caution-border bg-caution-surface text-caution-text")}>
          <RiRefreshLine className="size-3.5 animate-spin [animation-duration:1.4s]" aria-hidden />
        </span>
      );
    case "running":
    case "scheduled":
      return (
        <span className={cx(base, "border border-accent-300 bg-background-primary-default")}>
          <span className="size-3.5 animate-spin rounded-full border-2 border-accent-200 border-t-accent-600" aria-hidden />
        </span>
      );
    default:
      return (
        <span className={cx(base, "border border-dashed border-border-button-hover bg-background-primary-default")}>
          <span className="size-1.5 rounded-full bg-foreground-icon-quaternary" aria-hidden />
        </span>
      );
  }
}

const STATUS_TEXT: Record<string, string> = {
  pending: "Queued",
  scheduled: "Scheduled",
  running: "Running",
  retrying: "Backing off",
  completed: "Done",
  failed: "Failed",
};

export function StepTimeline({ steps, dense = false }: { steps: WorkflowStep[]; dense?: boolean }) {
  return (
    <ol className="relative flex flex-col" aria-label="Workflow steps">
      {steps.map((step, i) => {
        const { label, target } = stepLabel(step.name);
        const flag = stepFlag(step);
        const last = i === steps.length - 1;
        const dur = durationMs(step.started_at, step.ended_at);
        const err = step.error;
        const errTone = step.status === "failed" ? "stop" : flag === "resumed" ? "ink" : "caution";
        return (
          <li key={`${step.name}-${i}`} className={cx("relative flex gap-3", dense ? "pb-3" : "pb-4", last && "pb-0")}>
            {!last && <span aria-hidden className={cx("absolute start-3 top-6 bottom-0 w-px -translate-x-1/2", step.status === "completed" ? "bg-accent-300" : "bg-separator-border")} />}
            <StepIcon step={step} />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5 pt-0.5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className={cx("text-body-medium", step.status === "pending" ? "text-text-tertiary" : "text-text-primary")}>{label}</span>
                <code className="hidden font-mono text-caption-1-regular text-text-tertiary sm:inline">{step.name.split(":")[0]}</code>
                {target && <span className="rounded-md bg-background-secondary-default px-1.5 py-px font-mono text-caption-1-medium text-text-secondary">{target}</span>}
                {step.attempt > 1 && (
                  <span className="rounded-md border border-caution-border bg-caution-surface px-1.5 py-px font-mono text-caption-1-medium text-caution-text">attempt {step.attempt}</span>
                )}
                {flag === "retried" && (
                  <Chip variant="caption" color="yellow" className="gap-1">
                    <RiRefreshLine className="size-3" aria-hidden /> Retried
                  </Chip>
                )}
                {flag === "resumed" && (
                  <Chip variant="caption" color="blue" className="gap-1">
                    <RiRestartLine className="size-3" aria-hidden /> Resumed after worker crash
                  </Chip>
                )}
                {flag === "snapshot" && (
                  <Chip variant="caption" color="soft" className="gap-1">
                    <RiArchiveDrawerLine className="size-3" aria-hidden /> Cached snapshot
                  </Chip>
                )}
                <span className="ms-auto flex items-center gap-2 font-mono text-caption-1-regular text-text-tertiary rd-num">
                  <span>{STATUS_TEXT[step.status] ?? step.status}</span>
                  {dur !== null && <span className="text-text-secondary">{formatDuration(dur)}</span>}
                </span>
              </div>
              {step.note && <p className="font-mono text-caption-1-regular break-words text-text-tertiary">{step.note}</p>}
              {err && (
                <p
                  className={cx(
                    "rounded-lg border-s-2 px-2.5 py-1.5 font-mono text-caption-1-regular break-words",
                    errTone === "stop" && "border-stop-solid bg-stop-surface text-stop-text",
                    errTone === "caution" && "border-caution-solid bg-caution-surface text-caution-text",
                    errTone === "ink" && "border-accent-500 bg-background-secondary-default text-text-primary",
                  )}
                >
                  {err}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

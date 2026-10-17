"use client";

import { useSyncExternalStore } from "react";
import { Focusable } from "react-aria-components";
import { Tooltip, TooltipTrigger } from "@/components/base/tooltip/tooltip";
import { API_BASE, dataSourceStore } from "@/lib/api";
import { cx } from "@/utils/cx";

/** Subtle badge: "Live API" when connected and real, "Demo data" otherwise. */
export function DataSourceChip({ className }: { className?: string }) {
  const state = useSyncExternalStore(dataSourceStore.subscribe, dataSourceStore.get, () => null);
  if (!state) {
    return (
      <span className={cx("rd-source-chip inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-caption-1-medium text-text-tertiary", className)}>
        <span className="size-1.5 rounded-full bg-foreground-icon-quaternary" aria-hidden />
        Connecting…
      </span>
    );
  }
  const live = state.source === "live" && !state.placeholder;
  const label = live ? "Live API" : "Demo data";
  const tip = live
    ? `Connected to ${API_BASE}`
    : state.source === "live"
      ? "API connected, but some numbers are placeholders until the real run lands."
      : "API unreachable: showing recorded fixtures. Recalls are real CPSC data; listings, scan counts and eval numbers are placeholders.";
  return (
    <TooltipTrigger delay={150}>
      <Focusable>
        <span
          tabIndex={0}
          role="status"
          className={cx(
            "rd-source-chip inline-flex h-6 cursor-default items-center gap-1.5 rounded-full border px-2 text-caption-1-medium whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
            live ? "border-clear-border bg-clear-surface text-clear-text" : "border-caution-border bg-caution-surface text-caution-text",
            className,
          )}
        >
          <span className={cx("relative size-1.5 rounded-full", live ? "rd-pulse bg-clear-solid text-clear-solid" : "bg-caution-solid")} aria-hidden />
          {label}
        </span>
      </Focusable>
      <Tooltip size="md" placement="bottom">
        {tip}
      </Tooltip>
    </TooltipTrigger>
  );
}

/** Inline marker for a panel whose numbers are placeholders. */
export function PlaceholderNote({ show, children, className }: { show: boolean; children?: React.ReactNode; className?: string }) {
  if (!show) return null;
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md border border-dashed border-caution-border px-1.5 py-0.5 text-caption-1-medium text-caution-text", className)}>
      <span className="size-1.5 rounded-full bg-caution-solid" aria-hidden />
      {children ?? "Placeholder numbers"}
    </span>
  );
}

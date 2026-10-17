"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useCountUp } from "@/hooks/use-count-up";
import { cx } from "@/utils/cx";
import { Dot, IconTile, Skeleton, type Icon, type Tone } from "./surface";

/**
 * KPI card (BoardUI stat-cards recipe: soft icon tile, label, display value),
 * plus a coloured status dot and a caption line. Numbers count up on load.
 */
export function KpiCard({
  icon,
  tone = "blue",
  label,
  value,
  format = (n) => n.toLocaleString("en-US"),
  display,
  caption,
  status,
  badge,
  loading = false,
  index = 0,
  className,
}: {
  icon: Icon;
  tone?: Tone;
  label: ReactNode;
  /** Numeric value: animates. */
  value?: number | null;
  format?: (n: number) => string;
  /** Non-numeric value (e.g. "72/72", "$0.22"): shown as-is. */
  display?: ReactNode;
  caption?: ReactNode;
  /** Text next to the status dot (top-right). */
  status?: ReactNode;
  badge?: ReactNode;
  loading?: boolean;
  index?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const n = useCountUp(loading || value == null ? 0 : value, 900);
  const shown = display ?? (value == null ? "—" : format(reduce ? value : n));
  return (
    <motion.section
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className={cx("flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-card p-3.5 shadow-card sm:gap-4 sm:p-5", className)}
    >
      <div className="flex items-start justify-between gap-2">
        <IconTile icon={icon} tone={tone} size="md" />
        <span className="flex min-w-0 items-center gap-1.5 text-caption-1-medium text-text-tertiary">
          {badge}
          {status !== undefined && (
            <>
              <Dot tone={tone} />
              <span className="hidden truncate sm:inline">{status}</span>
            </>
          )}
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="line-clamp-2 text-body-2-medium text-text-secondary sm:truncate sm:text-body-medium">{label}</p>
        {loading ? (
          <Skeleton className="my-1 h-7 w-20" />
        ) : (
          <p className="truncate text-title-1-semibold tracking-[-0.02em] text-text-primary tabular-nums sm:text-display-4-semibold sm:leading-9">{shown}</p>
        )}
        {caption && <div className="line-clamp-2 text-caption-1-regular text-text-tertiary sm:truncate">{caption}</div>}
      </div>
    </motion.section>
  );
}

export function KpiRow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("grid grid-cols-2 gap-3 xl:grid-cols-4 xl:gap-4", className)}>{children}</div>;
}

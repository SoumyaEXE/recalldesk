import type { ComponentType, ReactNode } from "react";
import { VerdictGlyph } from "@/components/rd/verdict";
import { VERDICT_LABEL } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cx } from "@/utils/cx";

export type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
export type Tone = "blue" | "green" | "amber" | "red" | "gray" | "violet";

/* ----- Card ------------------------------------------------------------------ */

export function Card({ children, className, as: As = "section", ...rest }: { children: ReactNode; className?: string; as?: "section" | "div" | "article" | "aside"; "aria-label"?: string; "aria-labelledby"?: string; id?: string }) {
  return (
    <As className={cx("min-w-0 rounded-xl border border-line bg-card shadow-card", className)} {...rest}>
      {children}
    </As>
  );
}

export function CardHeader({ title, description, actions, icon: I, className, id }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; icon?: Icon; className?: string; id?: string }) {
  return (
    <div className={cx("flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3", className)}>
      <div className="flex min-w-0 items-start gap-3">
        {I && <IconTile icon={I} size="sm" />}
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 id={id} className="text-headline-semibold text-text-primary">
            {title}
          </h2>
          {description && <div className="text-body-2-regular text-text-tertiary">{description}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ----- Icon tile ------------------------------------------------------------- */

const TILE: Record<Tone, string> = {
  blue: "bg-info-surface text-info-text ring-info-border",
  green: "bg-clear-surface text-clear-text ring-clear-border",
  amber: "bg-caution-surface text-caution-text ring-caution-border",
  red: "bg-stop-surface text-stop-text ring-stop-border",
  gray: "bg-subtle text-text-secondary ring-line",
  violet: "bg-chart-4/10 text-chart-4-active ring-chart-4/25",
};

export function IconTile({ icon: I, tone = "gray", size = "md", className }: { icon: Icon; tone?: Tone; size?: "sm" | "md" | "lg"; className?: string }) {
  return (
    <span
      className={cx(
        "flex shrink-0 items-center justify-center ring-1 ring-inset",
        size === "sm" ? "size-8 rounded-lg" : size === "md" ? "size-10 rounded-[10px]" : "size-12 rounded-xl",
        TILE[tone],
        className,
      )}
      aria-hidden
    >
      <I className={size === "lg" ? "size-6" : size === "md" ? "size-5" : "size-[18px]"} aria-hidden />
    </span>
  );
}

/* ----- Status dot ------------------------------------------------------------ */

const DOT: Record<Tone, string> = {
  blue: "bg-info-solid",
  green: "bg-clear-solid",
  amber: "bg-caution-solid",
  red: "bg-stop-solid",
  gray: "bg-muted-solid",
  violet: "bg-chart-4",
};

export function Dot({ tone = "gray", pulse = false, className }: { tone?: Tone; pulse?: boolean; className?: string }) {
  return (
    <span className={cx("relative inline-flex size-2 shrink-0 rounded-full", DOT[tone], className)} aria-hidden>
      {pulse && <span className={cx("absolute inset-0 animate-ping rounded-full opacity-60", DOT[tone])} />}
    </span>
  );
}

/* ----- Pills ----------------------------------------------------------------- */

const PILL: Record<Tone, string> = {
  blue: "bg-info-surface text-info-text ring-info-border",
  green: "bg-clear-surface text-clear-text ring-clear-border",
  amber: "bg-caution-surface text-caution-text ring-caution-border",
  red: "bg-stop-surface text-stop-text ring-stop-border",
  gray: "bg-subtle text-text-secondary ring-line-strong",
  violet: TILE.violet,
};

export function Pill({ tone = "gray", children, dot = false, icon: I, className, size = "md" }: { tone?: Tone; children: ReactNode; dot?: boolean; icon?: Icon; className?: string; size?: "sm" | "md" }) {
  return (
    <span
      className={cx(
        "inline-flex w-fit items-center gap-1.5 rounded-full whitespace-nowrap ring-1 ring-inset",
        size === "sm" ? "h-5 px-2 text-caption-2-semibold" : "h-6 px-2.5 text-caption-1-semibold",
        PILL[tone],
        className,
      )}
    >
      {dot && <span className={cx("size-1.5 rounded-full", DOT[tone])} aria-hidden />}
      {I && <I className="size-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

export const VERDICT_TONE: Record<Verdict, Tone> = { match: "red", check: "amber", no_match: "green" };

/** Verdict pill: colour AND shape (octagon / triangle / circle) so it survives grayscale. */
export function VerdictPill({ verdict, size = "md", label, className }: { verdict: Verdict; size?: "sm" | "md"; label?: string; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex w-fit items-center gap-1.5 rounded-full whitespace-nowrap ring-1 ring-inset",
        size === "sm" ? "h-5 ps-1 pe-2 text-caption-2-semibold" : "h-6 ps-1.5 pe-2.5 text-caption-1-semibold",
        PILL[VERDICT_TONE[verdict]],
        className,
      )}
    >
      <VerdictGlyph verdict={verdict} className={size === "sm" ? "size-3" : "size-3.5"} />
      {label ?? VERDICT_LABEL[verdict]}
    </span>
  );
}

export function ChildrensPill({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <Pill tone="blue" size={size} dot>
      Children&apos;s
    </Pill>
  );
}

/** Marks a panel whose numbers are placeholders (drives honesty, not decoration). */
export function DemoBadge({ show = true, children = "Demo", className }: { show?: boolean; children?: ReactNode; className?: string }) {
  if (!show) return null;
  return (
    <span className={cx("inline-flex h-5 w-fit items-center gap-1 rounded-md border border-dashed border-caution-border bg-caution-surface px-1.5 text-caption-2-semibold whitespace-nowrap text-caution-text", className)}>
      <span className="size-1.5 rounded-full bg-caution-solid" aria-hidden />
      {children}
    </span>
  );
}

/* ----- Misc ------------------------------------------------------------------ */

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <code className={cx("rd-mono text-[0.92em] text-text-primary", className)}>{children}</code>;
}

export function IdChip({ children, tone = "amber" }: { children: ReactNode; tone?: "amber" | "gray" }) {
  return (
    <code
      className={cx(
        "rd-mono inline-flex h-6 items-center rounded-md px-1.5 text-caption-1-medium ring-1 ring-inset",
        tone === "amber" ? "bg-caution-surface text-text-primary ring-caution-border" : "bg-subtle text-text-primary ring-line-strong",
      )}
    >
      {children}
    </code>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cx("rd-skeleton block rounded-md", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx("flex flex-col", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex h-16 items-center gap-3 border-b border-line px-5 last:border-b-0">
          <Skeleton className="size-9 rounded-lg" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-3 w-2/5" />
            <Skeleton className="h-2.5 w-1/4" />
          </div>
          <Skeleton className="hidden h-5 w-20 rounded-full sm:block" />
          <Skeleton className="hidden h-3 w-16 md:block" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ icon: I, title, children, action, className, tone = "gray" }: { icon: Icon; title: ReactNode; children?: ReactNode; action?: ReactNode; className?: string; tone?: Tone }) {
  return (
    <div className={cx("flex flex-col items-center justify-center gap-3 px-6 py-12 text-center", className)}>
      <span className="relative flex items-center justify-center" aria-hidden>
        <span className="absolute size-20 rounded-full bg-subtle" />
        <span className="absolute size-14 rounded-full border border-dashed border-line-strong" />
        <IconTile icon={I} tone={tone} size="md" className="relative" />
      </span>
      <div className="mt-3 flex max-w-[380px] flex-col gap-1">
        <p className="text-headline-semibold text-text-primary">{title}</p>
        {children && <div className="text-body-2-regular text-text-tertiary">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function KeyValue({ k, children, className }: { k: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cx("grid grid-cols-[108px_minmax(0,1fr)] gap-3 py-2", className)}>
      <dt className="text-caption-1-medium text-text-tertiary">{k}</dt>
      <dd className="min-w-0 text-body-2-regular break-words text-text-primary">{children}</dd>
    </div>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase", className)}>{children}</p>;
}

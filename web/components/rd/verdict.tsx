import type { Verdict } from "@/lib/types";
import { VERDICT_LABEL, VERDICT_SHORT } from "@/lib/format";
import { cx } from "@/utils/cx";

/**
 * Each signal pairs a colour with a distinct shape so it survives grayscale
 * printing and colour-vision deficiency: octagon = DO NOT SELL, triangle =
 * CHECK LABEL, circle = clear.
 */
export function VerdictGlyph({ verdict, className, inverse = false }: { verdict: Verdict; className?: string; inverse?: boolean }) {
  const common = { className: cx("shrink-0", className), viewBox: "0 0 24 24", "aria-hidden": true } as const;
  if (verdict === "match") {
    return (
      <svg {...common}>
        <path d="M8 1.5h8L22.5 8v8L16 22.5H8L1.5 16V8z" className={inverse ? "fill-white" : "fill-stop-solid"} />
        <rect x="6" y="10.5" width="12" height="3" rx="0.6" className={inverse ? "fill-stop-solid" : "fill-white"} />
      </svg>
    );
  }
  if (verdict === "check") {
    return (
      <svg {...common}>
        <path d="M12 2 23 21.5H1z" strokeLinejoin="round" strokeWidth="1.5" className={inverse ? "fill-caution-ink stroke-caution-ink" : "fill-caution-solid stroke-caution-solid"} />
        <rect x="10.8" y="8.2" width="2.4" height="7.4" rx="1" className={inverse ? "fill-caution-solid" : "fill-caution-ink"} />
        <circle cx="12" cy="18.3" r="1.35" className={inverse ? "fill-caution-solid" : "fill-caution-ink"} />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="10.5" className="fill-clear-solid" />
      <path d="m7.2 12.4 3.2 3.1 6.4-6.6" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function VerdictBadge({ verdict, size = "md", short = false, className }: { verdict: Verdict; size?: "sm" | "md"; short?: boolean; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md border whitespace-nowrap",
        size === "sm" ? "h-6 px-1.5 text-caption-1-semibold" : "h-7 px-2 text-body-2-semibold",
        verdict === "match" && "border-stop-border bg-stop-surface text-stop-text",
        verdict === "check" && "border-caution-border bg-caution-surface text-caution-text",
        verdict === "no_match" && "border-clear-border bg-clear-surface text-clear-text",
        className,
      )}
    >
      <VerdictGlyph verdict={verdict} className={size === "sm" ? "size-3.5" : "size-4"} />
      {short ? VERDICT_SHORT[verdict] : VERDICT_LABEL[verdict]}
    </span>
  );
}

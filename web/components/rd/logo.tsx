import { cx } from "@/utils/cx";

/** A consignment hang-tag with a check notch: "before you list it, check it". */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("size-8 shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="9" className="fill-accent-700" />
      <path d="M9 9.5h9.2l6.3 6.3a1.6 1.6 0 0 1 0 2.3l-6.4 6.4a1.6 1.6 0 0 1-2.3 0L9.5 18.2V9.5z" fill="#fffdf8" transform="rotate(-8 16 16)" />
      <circle cx="13" cy="13.2" r="1.6" className="fill-accent-700" transform="rotate(-8 16 16)" />
      <path d="m14.6 18.3 2.1 2.1 4.1-4.3" fill="none" stroke="#c8102e" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" transform="rotate(-8 16 16)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("flex items-center gap-2", className)}>
      <LogoMark />
      <span className="flex flex-col leading-none">
        <span className="rd-notice text-[19px] leading-5 tracking-[0.03em] text-text-primary">RecallDesk</span>
        <span className="text-caption-2-medium text-text-tertiary">Check it before you list it</span>
      </span>
    </span>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type ComponentType, type ReactNode } from "react";
import {
  RiCloseLine,
  RiFileList3Line,
  RiFlaskLine,
  RiInformationLine,
  RiMenuLine,
  RiNodeTree,
  RiSearchEyeLine,
  RiStackLine,
  RiStore2Line,
} from "@remixicon/react";
import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { IconButton } from "@/components/base/buttons/icon-button";
import { Kbd } from "@/components/base/kbd/kbd";
import { DEMO_SHOP_NAME } from "@/lib/api";
import { cx } from "@/utils/cx";
import { DataSourceChip } from "./data-source-chip";
import { Wordmark } from "./logo";

type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

export const NAV: { href: string; label: string; icon: Icon; hint: string }[] = [
  { href: "/", label: "This week", icon: RiFileList3Line, hint: "1" },
  { href: "/check", label: "Check items", icon: RiStackLine, hint: "2" },
  { href: "/recalls", label: "Recalls", icon: RiStore2Line, hint: "3" },
  { href: "/scan", label: "eBay scan", icon: RiSearchEyeLine, hint: "4" },
  { href: "/lab", label: "Model Lab", icon: RiFlaskLine, hint: "5" },
  { href: "/runs", label: "Workflow runs", icon: RiNodeTree, hint: "6" },
  { href: "/about", label: "About & pricing", icon: RiInformationLine, hint: "7" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5">
      {NAV.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cx(
              "group flex items-center justify-between rounded-2lg p-2 outline-none",
              "transition-colors duration-150 ease focus-visible:ring-2 focus-visible:ring-border-focus-ring",
              active ? "bg-linear-to-b from-accent-600 to-accent-700 shadow-nav-selected" : "hover:bg-background-secondary-hover",
            )}
          >
            <span className="flex min-w-0 items-center gap-2">
              <Icon className={cx("size-5 shrink-0", active ? "text-white" : "text-foreground-icon-secondary")} aria-hidden />
              <span className={cx("text-body-medium whitespace-nowrap", active ? "text-white" : "text-text-secondary group-hover:text-text-primary")}>{item.label}</span>
            </span>
            <Kbd className={cx("hidden min-w-5 lg:inline-flex", active && "bg-white/20 text-white")}>{item.hint}</Kbd>
          </Link>
        );
      })}
    </nav>
  );
}

/** Next Thursday 2:00 PM America/New_York — when the WeeklyRecallSweep schedule fires. */
function nextSweep(now = new Date()): string {
  const d = new Date(now);
  const day = d.getUTCDay();
  let add = (4 - day + 7) % 7;
  if (add === 0 && d.getUTCHours() >= 18) add = 7;
  d.setUTCDate(d.getUTCDate() + add);
  return `${d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })} · 2:00 PM ET`;
}
const noop = () => () => {};

function ShopCard() {
  const sweep = useSyncExternalStore(noop, () => nextSweep(), () => null);
  return (
    <div className="rounded-2xl border border-border-button-default bg-background-primary-default p-3">
      <p className="rd-eyebrow text-text-tertiary">Watching for</p>
      <p className="mt-1 text-body-2-semibold text-text-primary">{DEMO_SHOP_NAME}</p>
      <p className="mt-2 flex flex-col gap-0.5">
        <span className="flex items-center gap-1.5 text-caption-1-medium text-text-tertiary">
          <span className="relative size-1.5 rounded-full bg-accent-500" aria-hidden />
          Next sweep
        </span>
        <span className="rd-num font-mono text-caption-1-medium text-text-primary">{sweep ?? "Thu · 2:00 PM ET"}</span>
      </p>
      <p className="mt-1 text-caption-1-regular text-text-tertiary">After CPSC posts on Thursday. Then it goes quiet.</p>
    </div>
  );
}

function SidebarBody({ onNavigate, mobile }: { onNavigate?: () => void; mobile?: boolean }) {
  return (
    <div className="flex h-full flex-col justify-between gap-6">
      <div className="flex flex-col gap-5">
        {!mobile && (
          <Link href="/" className="rounded-2lg p-1 outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring">
            <Wordmark />
          </Link>
        )}
        <NavList onNavigate={onNavigate} />
      </div>
      <div className="flex flex-col gap-3">
        <ShopCard />
        <div className="flex items-center justify-between gap-2 px-1">
          <DataSourceChip />
          <ThemeToggle appearance="sidebar-segmented" size="small" />
        </div>
      </div>
    </div>
  );
}

function useGlobalShortcuts() {
  const router = useRouter();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.closest("[role='listbox'],[role='dialog'],[role='grid']"))) return;
      const item = NAV.find((n) => n.hint === e.key);
      if (item) {
        e.preventDefault();
        router.push(item.href);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);
}

function useCleanMode() {
  useEffect(() => {
    try {
      if (new URLSearchParams(window.location.search).get("clean") === "1") document.documentElement.classList.add("rd-clean");
    } catch {
      /* ignore */
    }
  }, []);
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useGlobalShortcuts();
  useCleanMode();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <div className="min-h-dvh bg-background-full">
      <a href="#main" className="rd-no-print sr-only z-50 rounded-lg bg-background-primary-default px-3 py-2 text-body-medium focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to content
      </a>

      <header className="rd-no-print sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-separator-border bg-background-full/85 px-4 backdrop-blur-md lg:hidden">
        <Link href="/" className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring">
          <Wordmark />
        </Link>
        <div className="flex items-center gap-2">
          <DataSourceChip className="hidden min-[380px]:inline-flex" />
          <IconButton icon={RiMenuLine} size="small" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(true)} />
        </div>
      </header>

      <div className={cx("rd-no-print fixed inset-0 z-40 lg:hidden", open ? "pointer-events-auto" : "pointer-events-none")} aria-hidden={!open}>
        <div className={cx("absolute inset-0 bg-black/40 transition-opacity duration-200", open ? "opacity-100" : "opacity-0")} onClick={() => setOpen(false)} />
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className={cx(
            "absolute inset-y-2 start-2 flex w-[min(300px,calc(100vw-32px))] flex-col gap-4 rounded-3xl border border-border-button-white bg-background-secondary-default p-3 shadow-sidebar",
            "transition-transform duration-300 ease-out",
            open ? "translate-x-0" : "-translate-x-[110%]",
          )}
        >
          <div className="flex items-center justify-between p-1">
            <Wordmark />
            <IconButton icon={RiCloseLine} size="small" aria-label="Close navigation" onClick={() => setOpen(false)} tabIndex={open ? 0 : -1} />
          </div>
          <div className="min-h-0 flex-1">{open && <SidebarBody mobile onNavigate={() => setOpen(false)} />}</div>
        </div>
      </div>

      <div className="flex lg:gap-3 lg:p-3">
        <aside className="rd-no-print sticky top-3 hidden h-[calc(100dvh-24px)] w-[248px] shrink-0 overflow-y-auto rounded-3xl border border-border-button-white bg-background-secondary-default p-3 shadow-sidebar lg:block">
          <SidebarBody />
        </aside>
        <main id="main" key={pathname} className="rd-print-root min-w-0 flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}

export function Page({ children, className, wide }: { children: ReactNode; className?: string; wide?: boolean }) {
  return <div className={cx("rd-print-root mx-auto w-full px-4 pt-6 pb-16 sm:px-6 lg:px-8 lg:pt-8", wide ? "max-w-[1360px]" : "max-w-[1200px]", className)}>{children}</div>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="rd-no-print mb-6 flex flex-col gap-4 sm:mb-8 md:flex-row md:items-end md:justify-between">
      <div className="flex min-w-0 flex-col gap-1.5">
        {eyebrow && <p className="rd-eyebrow text-text-tertiary">{eyebrow}</p>}
        <h1 className="text-title-2-semibold text-balance text-text-primary sm:text-title-1-semibold">{title}</h1>
        {description && <p className="max-w-[680px] text-body-regular text-text-secondary">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  children,
  className,
  title,
  description,
  actions,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  padded?: boolean;
}) {
  return (
    <section className={cx("min-w-0 rounded-2xl border border-border-button-default bg-background-primary-default shadow-card", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-separator-border px-4 py-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            {title && <h2 className="text-headline-semibold text-text-primary">{title}</h2>}
            {description && <p className="text-body-2-regular text-text-secondary">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2 max-sm:w-full">{actions}</div>}
        </div>
      )}
      <div className={cx(padded && "p-4")}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "stop" | "caution" | "ink"; className?: string }) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-1 rounded-2xl border border-border-button-default bg-background-primary-default px-4 py-3", className)}>
      <span className="text-caption-1-medium text-text-tertiary">{label}</span>
      <span
        className={cx(
          "rd-figure text-[30px] leading-9",
          tone === "stop" ? "text-stop-text" : tone === "caution" ? "text-caution-text" : tone === "ink" ? "text-ink" : "text-text-primary",
        )}
      >
        {value}
      </span>
      {hint && <span className="text-caption-1-regular text-text-tertiary">{hint}</span>}
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Dialog as AriaDialog, Modal, ModalOverlay } from "react-aria-components";
import { CloseButton } from "@/components/base/buttons/close-button";
import { CommandPalette } from "@/components/shell/command-palette";
import { SidebarBody } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardHeader } from "@/components/ui/surface";
import { Toaster } from "@/components/ui/toast";
import { getRecalls } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

function useCleanMode() {
  useEffect(() => {
    try {
      if (new URLSearchParams(window.location.search).get("clean") === "1") document.documentElement.classList.add("rd-clean");
    } catch {
      /* ignore */
    }
  }, []);
}

/**
 * Framed desktop-app shell: soft gray canvas, one large rounded white frame,
 * a 248px left sidebar (drawer below 1024px) and a top bar.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();
  const recalls = useLoad(getRecalls, "recalls");
  useCleanMode();

  const week = useMemo(() => {
    const list = recalls.data ?? [];
    const latest = list.reduce((m, r) => (r.recall_date > m ? r.recall_date : m), "");
    return list.filter((r) => r.recall_date === latest);
  }, [recalls.data]);

  return (
    <div className="rd-shell min-h-dvh bg-canvas lg:p-3">
      <a href="#main" className="rd-no-print sr-only z-[70] rounded-lg bg-frame px-3 py-2 text-body-medium text-text-primary focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to content
      </a>
      <div className="rd-frame mx-auto flex min-h-dvh max-w-[1720px] overflow-clip bg-frame lg:min-h-[calc(100dvh-24px)] lg:rounded-[20px] lg:border lg:border-line lg:shadow-frame">
        <aside aria-label="Sidebar" className="rd-no-print hidden w-[248px] shrink-0 border-e border-line lg:block">
          <div className="sticky top-0 h-dvh lg:top-3 lg:h-[calc(100dvh-24px)]">
            <SidebarBody newRecalls={week.length} />
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar week={week} onMenu={() => setNavOpen(true)} />
          <main id="main" key={pathname} className="rd-print-root min-w-0 flex-1">
            {children}
          </main>
        </div>
      </div>

      <ModalOverlay isOpen={navOpen} onOpenChange={setNavOpen} isDismissable className="rd-overlay rd-no-print fixed inset-0 z-50 bg-neutral-950/35 backdrop-blur-[2px] lg:hidden">
        <Modal className="rd-navdrawer fixed inset-y-0 start-0 w-[min(300px,calc(100vw-48px))] border-e border-line bg-frame shadow-pop outline-none">
          <AriaDialog aria-label="Navigation" className="relative h-full outline-none">
            <CloseButton size="sm" aria-label="Close navigation" onClick={() => setNavOpen(false)} className="absolute top-4 -end-10 bg-frame" />
            <SidebarBody newRecalls={week.length} onNavigate={() => setNavOpen(false)} />
          </AriaDialog>
        </Modal>
      </ModalOverlay>

      <CommandPalette />
      <Toaster />
    </div>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string; wide?: boolean }) {
  return <div className={cx("rd-print-root mx-auto w-full max-w-[1440px] px-4 pt-6 pb-16 sm:px-6 lg:px-8 lg:pt-7", className)}>{children}</div>;
}

export function PageHeader({ title, description, actions, eyebrow }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="rd-no-print mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow && <div className="mb-1 flex flex-wrap items-center gap-2">{eyebrow}</div>}
        <h1 className="text-title-1-semibold tracking-[-0.015em] text-balance text-text-primary">{title}</h1>
        {description && <p className="max-w-[720px] text-body-regular text-text-tertiary">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Back-compat panel: a Card with an optional header. */
export function Panel({ children, className, title, description, actions, padded = true }: { children: ReactNode; className?: string; title?: ReactNode; description?: ReactNode; actions?: ReactNode; padded?: boolean }) {
  return (
    <Card className={className}>
      {(title || actions) && <CardHeader title={title} description={description} actions={actions} className="border-b border-line" />}
      <div className={cx(padded && "p-5")}>{children}</div>
    </Card>
  );
}

/** Back-compat small stat tile. */
export function Stat({ label, value, hint, tone, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "stop" | "caution" | "ink"; className?: string }) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-card px-4 py-3 shadow-card", className)}>
      <span className="text-caption-1-medium text-text-tertiary">{label}</span>
      <span className={cx("text-title-1-semibold tabular-nums", tone === "stop" ? "text-stop-text" : tone === "caution" ? "text-caution-text" : tone === "ink" ? "text-ink" : "text-text-primary")}>{value}</span>
      {hint && <span className="text-caption-1-regular text-text-tertiary">{hint}</span>}
    </div>
  );
}

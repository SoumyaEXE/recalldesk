"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Dialog as AriaDialog, Modal, ModalOverlay } from "react-aria-components";
import { RiArrowRightUpLine, RiCornerDownLeftLine, RiFileWarningLine, RiSearchLine } from "@remixicon/react";
import { Kbd } from "@/components/base/kbd/kbd";
import { getRecalls } from "@/lib/api";
import { shortTitle } from "@/lib/format";
import type { RecallRecord } from "@/lib/types";
import { cx } from "@/utils/cx";
import { ALL_NAV } from "./nav";

/* open state lives outside React so the sidebar, top bar and ⌘K all share it */
let open = false;
const subs = new Set<() => void>();
export function setPaletteOpen(v: boolean) {
  open = v;
  subs.forEach((s) => s());
}
const subscribe = (s: () => void) => {
  subs.add(s);
  return () => {
    subs.delete(s);
  };
};

type Entry = { id: string; group: string; label: string; sub?: string; href: string; icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>; mono?: string };

function idsOf(r: RecallRecord) {
  return [...(r.spec?.model_numbers ?? []), ...(r.spec?.other_identifiers ?? []), ...r.regex_ids, ...r.upcs];
}

export function CommandPalette() {
  const isOpen = useSyncExternalStore(subscribe, () => open, () => false);
  const router = useRouter();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [recalls, setRecalls] = useState<RecallRecord[]>([]);
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!open);
      } else if (e.key === "/" && !open) {
        const t = e.target as HTMLElement | null;
        if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!isOpen || recalls.length) return;
    getRecalls().then((r) => setRecalls(r.data), () => {});
  }, [isOpen, recalls.length]);

  const entries = useMemo<Entry[]>(() => {
    const t = q.trim().toLowerCase();
    const pages: Entry[] = ALL_NAV.filter((n) => !t || `${n.label} ${n.keywords ?? ""}`.toLowerCase().includes(t)).map((n) => ({ id: `p:${n.href}`, group: "Pages", label: n.label, href: n.href, icon: n.icon }));
    const rs: Entry[] = t
      ? recalls
          .filter((r) => `${r.recall_number} ${r.title} ${r.spec?.brand ?? ""} ${idsOf(r).join(" ")}`.toLowerCase().includes(t))
          .slice(0, 8)
          .map((r) => {
            const hit = idsOf(r).find((id) => id.toLowerCase().includes(t));
            return { id: `r:${r.recall_number}`, group: "Recalls", label: shortTitle(r.title), sub: r.spec?.brand ?? r.manufacturers[0], mono: hit ? `#${r.recall_number} · ${hit}` : `#${r.recall_number}`, href: `/recalls?open=${r.recall_number}`, icon: RiFileWarningLine };
          })
      : [];
    return [...pages, ...rs];
  }, [q, recalls]);

  const go = (e?: Entry) => {
    if (!e) return;
    setPaletteOpen(false);
    setQ("");
    router.push(e.href);
  };

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  let lastGroup = "";
  return (
    <ModalOverlay
      isOpen={isOpen}
      onOpenChange={(v) => {
        setPaletteOpen(v);
        if (!v) setQ("");
      }}
      isDismissable
      className="rd-overlay rd-no-print fixed inset-0 z-[60] flex items-start justify-center bg-neutral-950/30 px-3 pt-[12vh] backdrop-blur-[2px]"
    >
      <Modal className="rd-dialog w-full max-w-[600px] overflow-hidden rounded-2xl border border-line bg-frame shadow-pop outline-none">
        <AriaDialog aria-label="Command menu" className="outline-none">
          <div className="flex items-center gap-3 border-b border-line px-4">
            <RiSearchLine className="size-5 shrink-0 text-foreground-icon-tertiary" aria-hidden />
            <input
              autoFocus
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(entries.length - 1, a + 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(0, a - 1));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  go(entries[active]);
                }
              }}
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={entries[active] ? `${listId}-${active}` : undefined}
              aria-label="Search pages, recall numbers and model numbers"
              placeholder="Jump to a page, or search a recall #, brand or model number…"
              className="h-14 min-w-0 flex-1 bg-transparent text-body-regular text-text-primary outline-none placeholder:text-text-placeholder"
            />
            <Kbd className="rounded-md px-1.5">Esc</Kbd>
          </div>
          <ul ref={listRef} id={listId} role="listbox" aria-label="Results" className="rd-scroll max-h-[min(420px,60vh)] overflow-y-auto p-2">
            {entries.map((e, i) => {
              const header = e.group !== lastGroup ? e.group : null;
              lastGroup = e.group;
              const I = e.icon;
              return (
                <li key={e.id} role="presentation">
                  {header && <p className="px-2.5 pt-2 pb-1.5 text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase">{header}</p>}
                  <div
                    id={`${listId}-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => setActive(i)}
                    onClick={() => go(e)}
                    className={cx("flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2", i === active ? "bg-active-nav" : "")}
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-line bg-card">
                      <I className="size-4 text-foreground-icon-secondary" aria-hidden />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-body-2-medium text-text-primary">{e.label}</span>
                      {(e.sub || e.mono) && (
                        <span className="truncate text-caption-1-regular text-text-tertiary">
                          {e.mono && <span className="rd-mono">{e.mono}</span>}
                          {e.mono && e.sub && " · "}
                          {e.sub}
                        </span>
                      )}
                    </span>
                    {i === active ? <RiCornerDownLeftLine className="size-4 text-foreground-icon-tertiary" aria-hidden /> : <RiArrowRightUpLine className="size-4 text-foreground-icon-quaternary" aria-hidden />}
                  </div>
                </li>
              );
            })}
            {!entries.length && <li className="px-3 py-10 text-center text-body-2-regular text-text-tertiary">No pages or recalls match “{q}”.</li>}
          </ul>
          <div className="flex items-center gap-4 border-t border-line bg-subtle px-4 py-2 text-caption-1-regular text-text-tertiary">
            <span className="flex items-center gap-1.5">
              <Kbd className="rounded-md px-1.5">↑</Kbd>
              <Kbd className="rounded-md px-1.5">↓</Kbd> navigate
            </span>
            <span className="flex items-center gap-1.5">
              <Kbd className="rounded-md px-1.5">↵</Kbd> open
            </span>
            <span className="ms-auto">{recalls.length ? `${recalls.length} recalls indexed` : "Loading recalls…"}</span>
          </div>
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}

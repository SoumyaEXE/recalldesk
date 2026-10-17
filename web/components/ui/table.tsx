"use client";

import { useMemo, useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { RiArrowDownSLine, RiArrowRightSLine, RiArrowUpDownLine, RiArrowUpSLine, RiCheckLine, RiSearchLine } from "@remixicon/react";
import { Dropdown, DropdownItem, DropdownPopover, DropdownTrigger } from "@/components/base/dropdown/dropdown";
import { Pagination } from "@/components/base/pagination/pagination";
import { cx } from "@/utils/cx";
import { SkeletonRows, type Icon } from "./surface";

/* ----- Toolbar pieces --------------------------------------------------------- */

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("flex flex-col gap-3 border-b border-line px-4 py-3 sm:px-5 md:flex-row md:items-center md:justify-between", className)}>{children}</div>;
}

export function SearchField({ value, onChange, placeholder, label, className }: { value: string; onChange: (v: string) => void; placeholder: string; label: string; className?: string }) {
  return (
    <label className={cx("relative flex min-w-0 items-center", className)}>
      <span className="sr-only">{label}</span>
      <RiSearchLine className="pointer-events-none absolute start-3 size-4 text-foreground-icon-tertiary" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-lg border border-line bg-card ps-9 pe-3 text-body-2-regular text-text-primary shadow-card outline-none transition-colors placeholder:text-text-placeholder hover:border-line-strong focus-visible:border-accent-400 focus-visible:ring-3 focus-visible:ring-accent-500/15"
      />
    </label>
  );
}

export interface FilterOption<V extends string> {
  value: V;
  label: string;
  count?: number;
}

/** "Status: All ▾" filter pill (BoardUI Dropdown underneath). */
export function FilterPill<V extends string>({ label, value, options, onChange }: { label: string; value: V; options: FilterOption<V>[]; onChange: (v: V) => void }) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <Dropdown isOpen={open} onOpenChange={setOpen}>
      <DropdownTrigger
        aria-label={`${label}: ${current?.label ?? value}`}
        className={cx(
          "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border bg-card ps-3 pe-2 text-body-2-medium shadow-card transition-colors",
          open ? "border-accent-400" : "border-line hover:border-line-strong",
        )}
      >
        <span className="text-text-tertiary">{label}:</span>
        <span className="text-text-primary">{current?.label ?? value}</span>
        <RiArrowDownSLine className={cx("size-4 text-foreground-icon-tertiary transition-transform", open && "rotate-180")} aria-hidden />
      </DropdownTrigger>
      <DropdownPopover aria-label={label} placement="bottom end" className="w-[220px]">
        {options.map((o) => (
          <DropdownItem
            key={o.value}
            selected={o.value === value}
            onSelect={() => {
              onChange(o.value);
              setOpen(false);
            }}
            className="px-2 py-1.5"
          >
            <span className="flex-1 text-body-2-medium">{o.label}</span>
            {o.count !== undefined && <span className="text-caption-1-medium text-text-tertiary tabular-nums">{o.count}</span>}
            <RiCheckLine className={cx("size-4 text-accent-600", o.value === value ? "opacity-100" : "opacity-0")} aria-hidden />
          </DropdownItem>
        ))}
      </DropdownPopover>
    </Dropdown>
  );
}

/* ----- DataTable ---------------------------------------------------------------- */

export interface Column<T> {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  sort?: (row: T) => string | number;
  align?: "start" | "end";
  className?: string;
  /** Hide on md..lg desktops when space is tight. */
  hideBelow?: "lg" | "xl";
  /** Mobile stacked-card role: the headline, an inline badge, a labelled meta row, or hidden. */
  mobile?: "primary" | "badge" | "meta" | "hidden";
  /** Mobile label (defaults to header if it is a string). */
  mobileLabel?: string;
  width?: string;
}

type SortState = { id: string; dir: "asc" | "desc" } | null;

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowOpen,
  rowLabel,
  loading = false,
  empty,
  initialSort = null,
  pageSize = 10,
  caption,
  selectedKey,
  footerNote,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowOpen?: (row: T) => void;
  rowLabel?: (row: T) => string;
  loading?: boolean;
  empty?: ReactNode;
  initialSort?: SortState;
  pageSize?: number;
  caption: string;
  selectedKey?: string | null;
  footerNote?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const [sort, setSort] = useState<SortState>(initialSort);
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.id === sort.id);
    if (!col?.sort) return rows;
    const get = col.sort;
    return [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return sort.dir === "asc" ? r : -r;
    });
  }, [rows, columns, sort]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, totalPages);
  const visible = sorted.slice((current - 1) * pageSize, current * pageSize);
  const colHide = (c: Column<T>) => (c.hideBelow === "lg" ? "hidden lg:table-column" : c.hideBelow === "xl" ? "hidden xl:table-column" : "");
  const hide = (c: Column<T>) => (c.hideBelow === "lg" ? "hidden lg:table-cell" : c.hideBelow === "xl" ? "hidden xl:table-cell" : "");

  const toggle = (id: string) => {
    setPage(1);
    setSort((s) => (s?.id !== id ? { id, dir: "desc" } : s.dir === "desc" ? { id, dir: "asc" } : null));
  };

  if (loading) return <SkeletonRows rows={Math.min(pageSize, 6)} />;
  if (!rows.length) return <>{empty}</>;

  const primary = columns.find((c) => c.mobile === "primary") ?? columns[0];
  const badges = columns.filter((c) => c.mobile === "badge");
  const metas = columns.filter((c) => c !== primary && (c.mobile === "meta" || c.mobile === undefined));

  return (
    <div>
      {/* Desktop / tablet: a real table */}
      <div className="hidden md:block">
        <table className="w-full table-fixed border-collapse text-start">
          <caption className="sr-only">{caption}</caption>
          <colgroup>
            {columns.map((c) => (
              <col key={c.id} className={colHide(c)} style={c.width ? { width: c.width } : undefined} />
            ))}
            {onRowOpen && <col style={{ width: 44 }} />}
          </colgroup>
          <thead>
            <tr className="border-b border-line bg-subtle">
              {columns.map((c) => {
                const active = sort?.id === c.id;
                const SortIcon = !active ? RiArrowUpDownLine : sort.dir === "asc" ? RiArrowUpSLine : RiArrowDownSLine;
                return (
                  <th
                    key={c.id}
                    scope="col"
                    aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
                    className={cx("h-10 px-3 text-caption-2-semibold tracking-[0.06em] whitespace-nowrap text-text-tertiary uppercase first:ps-5", c.align === "end" ? "text-end" : "text-start", hide(c))}
                  >
                    {c.sort ? (
                      <button
                        type="button"
                        onClick={() => toggle(c.id)}
                        className={cx(
                          "inline-flex cursor-pointer items-center gap-1 rounded uppercase outline-none hover:text-text-primary focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                          active && "text-text-primary",
                          c.align === "end" && "flex-row-reverse",
                        )}
                      >
                        {c.header}
                        <SortIcon className={cx("size-3.5", active ? "text-text-primary" : "text-foreground-icon-quaternary")} aria-hidden />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
              {onRowOpen && (
                <th scope="col" className="w-11">
                  <span className="sr-only">Open</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => {
              const k = rowKey(row);
              const sel = selectedKey === k;
              return (
                <motion.tr
                  key={k}
                  initial={reduce ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.25, delay: Math.min(i, 10) * 0.02 }}
                  onClick={onRowOpen ? () => onRowOpen(row) : undefined}
                  className={cx(
                    "group border-b border-line transition-colors last:border-b-0",
                    onRowOpen && "cursor-pointer hover:bg-hover",
                    sel && "bg-hover",
                  )}
                >
                  {columns.map((c, ci) => (
                    <td key={c.id} className={cx("h-16 px-3 align-middle text-body-2-regular text-text-secondary first:ps-5", c.align === "end" && "text-end", hide(c), c.className)}>
                      {ci === 0 && onRowOpen ? (
                        <div className="relative min-w-0">
                          <button
                            type="button"
                            aria-label={rowLabel ? rowLabel(row) : "Open details"}
                            onClick={(e) => {
                              e.stopPropagation();
                              onRowOpen(row);
                            }}
                            className="absolute -inset-2 z-10 cursor-pointer rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring"
                          />
                          {c.cell(row)}
                        </div>
                      ) : (
                        c.cell(row)
                      )}
                    </td>
                  ))}
                  {onRowOpen && (
                    <td className="pe-4 text-end">
                      <RiArrowRightSLine className="ms-auto size-5 text-foreground-icon-quaternary transition-transform group-hover:translate-x-0.5 group-hover:text-foreground-icon-secondary" aria-hidden />
                    </td>
                  )}
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Phone: stacked cards */}
      <ul className="flex flex-col gap-2 p-3 md:hidden" aria-label={caption}>
        {visible.map((row) => {
          const k = rowKey(row);
          const body = (
            <>
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">{primary.cell(row)}</div>
                {onRowOpen && <RiArrowRightSLine className="mt-1 size-5 shrink-0 text-foreground-icon-tertiary" aria-hidden />}
              </div>
              {badges.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {badges.map((c) => (
                    <span key={c.id}>{c.cell(row)}</span>
                  ))}
                </div>
              )}
              {metas.length > 0 && (
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-line pt-2.5">
                  {metas.map((c) => (
                    <div key={c.id} className="flex min-w-0 flex-col gap-0.5">
                      <dt className="text-caption-2-semibold tracking-[0.05em] text-text-tertiary uppercase">{c.mobileLabel ?? (typeof c.header === "string" ? c.header : c.id)}</dt>
                      <dd className="min-w-0 text-body-2-regular text-text-secondary">{c.cell(row)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </>
          );
          return (
            <li key={k}>
              {onRowOpen ? (
                <button
                  type="button"
                  aria-label={rowLabel ? rowLabel(row) : "Open details"}
                  onClick={() => onRowOpen(row)}
                  className="flex w-full cursor-pointer flex-col gap-2.5 rounded-xl border border-line bg-card p-3.5 text-start shadow-card outline-none transition-colors active:bg-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
                >
                  {body}
                </button>
              ) : (
                <div className="flex flex-col gap-2.5 rounded-xl border border-line bg-card p-3.5 shadow-card">{body}</div>
              )}
            </li>
          );
        })}
      </ul>

      {(totalPages > 1 || footerNote) && (
        <div className="flex flex-col gap-3 border-t border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <p className="text-caption-1-regular whitespace-nowrap text-text-tertiary tabular-nums">
            {footerNote ?? (
              <>
                Showing {(current - 1) * pageSize + 1}–{Math.min(current * pageSize, sorted.length)} of {sorted.length}
              </>
            )}
          </p>
          {totalPages > 1 && <Pagination page={current} totalPages={totalPages} onChange={setPage} aria-label={`${caption} pages`} />}
        </div>
      )}
    </div>
  );
}

/** Leading avatar tile for table rows: product photo or initials. */
export function RowAvatar({ label, tone = "gray", src, alt = "", icon: I }: { label: string; tone?: "gray" | "blue" | "red" | "amber" | "green"; src?: string | null; alt?: string; icon?: Icon }) {
  const [failed, setFailed] = useState(false);
  const initials = label
    .replace(/[^A-Za-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
  const t = {
    gray: "bg-subtle text-text-secondary ring-line",
    blue: "bg-info-surface text-info-text ring-info-border",
    red: "bg-stop-surface text-stop-text ring-stop-border",
    amber: "bg-caution-surface text-caution-text ring-caution-border",
    green: "bg-clear-surface text-clear-text ring-clear-border",
  }[tone];
  return (
    <span className={cx("flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg text-caption-1-semibold ring-1 ring-inset", t)} aria-hidden={!alt}>
      {src && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={alt} width={36} height={36} decoding="async" onError={() => setFailed(true)} className="size-full bg-white object-contain" />
      ) : I ? (
        <I className="size-[18px]" aria-hidden />
      ) : (
        initials || "•"
      )}
    </span>
  );
}

export function RowTitle({ title, sub, leading }: { title: ReactNode; sub?: ReactNode; leading?: ReactNode }) {
  return (
    <span className="flex min-w-0 items-center gap-3">
      {leading}
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="line-clamp-2 text-body-2-semibold text-text-primary md:block md:truncate">{title}</span>
        {sub && <span className="truncate text-caption-1-regular text-text-tertiary">{sub}</span>}
      </span>
    </span>
  );
}

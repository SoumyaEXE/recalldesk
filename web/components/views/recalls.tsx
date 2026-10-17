"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { RiArrowDownSLine, RiExternalLinkLine, RiSearchLine } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Page, PageHeader, Stat } from "@/components/rd/app-shell";
import { PlaceholderNote } from "@/components/rd/data-source-chip";
import { HighlightIds } from "@/components/rd/ids";
import { getRecalls, getScan } from "@/lib/api";
import { formatDate, num, shortTitle, soldWindow } from "@/lib/format";
import type { RecallRecord, ScanByRecall } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

const GRID = "md:grid-cols-[88px_minmax(0,1fr)_120px_minmax(0,180px)_72px_88px_28px]";

function idsOf(r: RecallRecord) {
  return [...new Set([...(r.spec?.model_numbers ?? []), ...(r.spec?.other_identifiers ?? []), ...(r.spec?.upcs ?? []), ...r.regex_ids, ...r.upcs])];
}

function SpecRow({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[112px_minmax(0,1fr)] gap-3 py-1.5">
      <dt className="text-caption-1-semibold text-text-tertiary">{k}</dt>
      <dd className="min-w-0 text-body-2-regular text-text-primary">{children}</dd>
    </div>
  );
}

function IdChips({ ids }: { ids: string[] }) {
  if (!ids.length) return <span className="text-text-tertiary">None stated</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <code key={id} className="rounded border border-caution-border bg-caution-surface px-1.5 py-px font-mono text-caption-1-medium text-text-primary">
          {id}
        </code>
      ))}
    </span>
  );
}

function Expanded({ r }: { r: RecallRecord }) {
  const s = r.spec;
  return (
    <div className="grid gap-4 border-t border-separator-border bg-background-secondary-default/60 px-4 py-4 lg:grid-cols-2">
      <section className="flex min-w-0 flex-col gap-3">
        <h4 className="rd-eyebrow text-text-tertiary">Original CPSC text</h4>
        <p className="text-body-2-regular leading-6 text-text-primary">
          <HighlightIds text={r.description} ids={idsOf(r)} />
        </p>
        {r.retailers[0] && <p className="text-caption-1-regular text-text-secondary">{r.retailers.join(" ")}</p>}
        {r.hazards[0] && (
          <p className="text-caption-1-regular text-text-secondary">
            <span className="font-semibold text-stop-text">Hazard. </span>
            {r.hazards[0]}
          </p>
        )}
        {r.images.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {r.images.slice(0, 4).map((src) => (
              <Image key={src} src={src} alt={`CPSC photo for recall ${r.recall_number}`} width={96} height={96} unoptimized loading="lazy" className="size-24 rounded-lg border border-border-button-default bg-white object-contain" />
            ))}
          </div>
        )}
        <a href={r.url} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-caption-1-semibold text-ink hover:underline">
          Read on cpsc.gov <RiExternalLinkLine className="size-3.5" aria-hidden />
        </a>
      </section>
      <section className="flex min-w-0 flex-col gap-2 rounded-xl border border-border-button-default bg-background-primary-default p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="rd-eyebrow text-text-tertiary">Extracted RecallSpec</h4>
          {s?.spec_source && (
            <Chip variant="caption" color={s.spec_source === "teacher" ? "blue" : "soft"}>
              {s.spec_source === "teacher" ? "Teacher: Qwen3.5-397B" : s.spec_source}
            </Chip>
          )}
        </div>
        {s ? (
          <dl className="divide-y divide-separator-border">
            <SpecRow k="Brand">{s.brand}</SpecRow>
            <SpecRow k="Product">
              {s.product_name} <span className="text-text-tertiary">· {s.product_type}</span>
            </SpecRow>
            <SpecRow k="Model numbers">
              <IdChips ids={s.model_numbers} />
            </SpecRow>
            {(s.other_identifiers.length > 0 || s.upcs.length > 0) && (
              <SpecRow k="Other IDs / UPC">
                <IdChips ids={[...s.other_identifiers, ...s.upcs]} />
              </SpecRow>
            )}
            <SpecRow k="Sold">{soldWindow(s.sold_from, s.sold_to)}</SpecRow>
            {s.colors.length > 0 && <SpecRow k="Colors">{s.colors.join(", ")}</SpecRow>}
            {s.key_features.length > 0 && (
              <SpecRow k="Key features">
                <ul className="list-disc ps-4">
                  {s.key_features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </SpecRow>
            )}
            {s.look_for && (
              <SpecRow k="Look for">
                <span className="font-medium">
                  <HighlightIds text={s.look_for} />
                </span>
              </SpecRow>
            )}
            <SpecRow k="Hazard">{s.hazard_short}</SpecRow>
            <SpecRow k="Remedy">{s.remedy_short}</SpecRow>
            <SpecRow k="eBay queries">
              <span className="flex flex-col gap-0.5 font-mono text-caption-1-regular text-text-secondary">
                {s.search_queries.map((q) => (
                  <span key={q}>{q}</span>
                ))}
              </span>
            </SpecRow>
          </dl>
        ) : (
          <p className="text-body-2-regular text-text-tertiary">Spec not extracted yet.</p>
        )}
      </section>
    </div>
  );
}

function Row({ r, scan, open, onToggle }: { r: RecallRecord; scan?: ScanByRecall; open: boolean; onToggle: () => void }) {
  const id = `recall-${r.recall_number}`;
  return (
    <li className={cx("border-b border-separator-border last:border-b-0", open && "bg-background-primary-default")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`${open ? "Collapse" : "Expand"} recall ${r.recall_number}`}
        onClick={onToggle}
        className={cx("grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_28px] items-center gap-x-3 gap-y-1 px-4 py-3 text-start outline-none hover:bg-background-secondary-default/70 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-border-focus-ring", GRID)}
      >
        <span className="hidden font-mono text-caption-1-medium text-text-secondary rd-num md:block">{formatDate(r.recall_date, { month: "short", day: "numeric" })}</span>
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="text-body-2-semibold text-text-primary">{shortTitle(r.title)}</span>
          <span className="flex flex-wrap items-center gap-x-2 text-caption-1-regular text-text-tertiary">
            <span className="font-mono">#{r.recall_number}</span>
            <span className="md:hidden">{formatDate(r.recall_date, { month: "short", day: "numeric" })}</span>
            <span className="truncate">{r.spec?.brand}</span>
            {r.is_childrens && <span className="rounded bg-status-blue-background px-1 text-caption-2-semibold text-status-blue-text md:hidden">Kids</span>}
            {scan && (scan.match > 0 || scan.check > 0) && (
              <span className="md:hidden">
                · <span className="text-stop-text">{scan.match}</span> / <span className="text-caution-text">{scan.check}</span> flagged of {scan.listings}
              </span>
            )}
          </span>
        </span>
        <span className="hidden md:block">{r.is_childrens ? <span className="rounded bg-status-blue-background px-1.5 py-0.5 text-caption-1-semibold text-status-blue-text">Children&apos;s</span> : <span className="text-caption-1-regular text-text-tertiary">—</span>}</span>
        <span className="hidden min-w-0 text-caption-1-regular text-text-secondary md:block">
          <span className="block truncate">{r.spec?.hazard_short}</span>
          <span className="block truncate text-text-tertiary">{r.units ?? "Units not stated"}</span>
        </span>
        <span className="hidden text-end font-mono text-body-2-medium text-text-primary rd-num md:block">{scan ? num(scan.listings) : "—"}</span>
        <span className="hidden justify-end gap-1 font-mono text-body-2-semibold rd-num md:flex">
          {scan ? (
            <>
              <span className={scan.match ? "text-stop-text" : "text-text-tertiary"}>{scan.match}</span>
              <span className="text-text-tertiary">/</span>
              <span className={scan.check ? "text-caution-text" : "text-text-tertiary"}>{scan.check}</span>
            </>
          ) : (
            "—"
          )}
        </span>
        <RiArrowDownSLine className={cx("size-5 justify-self-end text-foreground-icon-secondary transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={id}>
          <Expanded r={r} />
        </div>
      )}
    </li>
  );
}

export function RecallsView() {
  const recalls = useLoad(getRecalls, "recalls");
  const scan = useLoad(getScan, "scan");
  const [q, setQ] = useState("");
  const [kids, setKids] = useState<"all" | "kids">("all");
  const [open, setOpen] = useState<string | null>(null);
  const [limit, setLimit] = useState(40);

  const scanBy = useMemo(() => new Map((scan.data?.by_recall ?? []).map((x) => [x.recall_number, x])), [scan.data]);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (recalls.data ?? [])
      .filter((r) => (kids === "kids" ? r.is_childrens : true))
      .filter((r) => !t || `${r.title} ${r.recall_number} ${r.spec?.brand} ${idsOf(r).join(" ")}`.toLowerCase().includes(t))
      .sort((a, b) => b.recall_date.localeCompare(a.recall_date) || b.recall_number.localeCompare(a.recall_number));
  }, [recalls.data, q, kids]);

  const all = recalls.data ?? [];
  const withIds = all.filter((r) => (r.spec?.model_numbers.length ?? 0) > 0 || r.regex_ids.length > 0).length;

  return (
    <Page wide>
      <PageHeader
        eyebrow="CPSC · since July 18, 2026"
        title="Recalls"
        description="Every CPSC recall since July 18. Open one to see the original text with its identifiers highlighted, next to the identification spec the teacher model extracted from it."
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Recalls" value={all.length || "…"} />
        <Stat label="Children's products" value={all.length ? all.filter((r) => r.is_childrens).length : "…"} tone="ink" />
        <Stat label="With model / lot IDs" value={all.length ? withIds : "…"} hint="buried in the description text" />
        <Stat label="eBay listings seen" value={scan.data ? num(scan.data.listings_seen) : "…"} hint={<PlaceholderNote show={scan.placeholder} />} />
      </div>

      <section className="rounded-2xl border border-border-button-default bg-background-primary-default shadow-card">
        <div className="flex flex-col gap-3 border-b border-separator-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="relative flex min-w-0 flex-1 items-center sm:max-w-sm">
            <span className="sr-only">Search recalls</span>
            <RiSearchLine className="pointer-events-none absolute start-2.5 size-4 text-foreground-icon-tertiary" aria-hidden />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Brand, product, model no., recall #"
              className="h-9 w-full rounded-lg border border-border-button-default bg-background-primary-default ps-8 pe-3 text-body-2-regular text-text-primary outline-none placeholder:text-text-placeholder hover:border-border-button-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
            />
          </label>
          <SegmentedControl aria-label="Filter" selectedKeys={[kids]} onSelectionChange={(k) => setKids(([...k][0] as "all" | "kids") ?? "all")}>
            <SegmentedControlItem id="all">All</SegmentedControlItem>
            <SegmentedControlItem id="kids">Children&apos;s</SegmentedControlItem>
          </SegmentedControl>
        </div>
        <div className={cx("hidden gap-x-3 border-b border-separator-border px-4 py-2 text-caption-1-semibold text-text-tertiary md:grid", GRID)} aria-hidden>
          <span>Date</span>
          <span>Recall</span>
          <span>Category</span>
          <span>Hazard · units</span>
          <span className="text-end">eBay</span>
          <span className="text-end">
            <span className="text-stop-text">Match</span> / <span className="text-caution-text">check</span>
          </span>
          <span />
        </div>
        {recalls.loading ? (
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-background-secondary-default" />
            ))}
          </div>
        ) : (
          <ul>
            {rows.slice(0, limit).map((r) => (
              <Row key={r.recall_number} r={r} scan={scanBy.get(r.recall_number)} open={open === r.recall_number} onToggle={() => setOpen(open === r.recall_number ? null : r.recall_number)} />
            ))}
            {!rows.length && <li className="px-4 py-10 text-center text-body-2-regular text-text-tertiary">No recalls match “{q}”.</li>}
          </ul>
        )}
        {rows.length > limit && (
          <div className="border-t border-separator-border px-4 py-3">
            <Button variant="secondary" size="small" onClick={() => setLimit((l) => l + 60)}>
              Show more ({rows.length - limit} left)
            </Button>
          </div>
        )}
      </section>
    </Page>
  );
}

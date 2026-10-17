"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { RiExternalLinkLine, RiImageLine, RiShieldCheckLine, RiUserLine } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Page, Panel } from "@/components/rd/app-shell";
import { PlaceholderNote } from "@/components/rd/data-source-chip";
import { VerdictBadge } from "@/components/rd/verdict";
import { getRecalls, getScan, getScanDetail } from "@/lib/api";
import { formatDate, num, shortTitle } from "@/lib/format";
import type { ScanByRecall, ScannedListing } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

function Big({ label, value, tone, sub }: { label: string; value: string; tone?: "stop" | "caution" | "ink"; sub?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 border-separator-border px-1 py-2 sm:border-s sm:ps-5 sm:first:border-s-0 sm:first:ps-1">
      <span className={cx("rd-figure text-[44px] sm:text-[56px]", tone === "stop" ? "text-stop-text" : tone === "caution" ? "text-caution-text" : tone === "ink" ? "text-ink" : "text-text-primary")}>{value}</span>
      <span className="text-body-2-semibold text-text-primary">{label}</span>
      {sub && <span className="text-caption-1-regular text-text-tertiary">{sub}</span>}
    </div>
  );
}

function ListingCard({ l }: { l: ScannedListing }) {
  return (
    <li className="flex min-w-0 gap-3 rounded-xl border border-border-button-default bg-background-primary-default p-3">
      <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border-button-default bg-background-secondary-default sm:size-24">
        {l.thumbnail ? (
          <Image src={l.thumbnail} alt="" width={96} height={96} unoptimized loading="lazy" className="size-full object-cover" />
        ) : (
          <RiImageLine className="size-6 text-foreground-icon-quaternary" aria-label="No photo" />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <VerdictBadge verdict={l.verdict.verdict} size="sm" />
          {l.human_verified && (
            <Chip variant="caption" color="blue" className="gap-1 py-0.5">
              <RiShieldCheckLine className="size-3" aria-hidden /> Human-verified
            </Chip>
          )}
        </div>
        <p className="text-body-2-semibold break-words text-text-primary">{l.title}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption-1-regular text-text-secondary">
          {l.price && <span className="font-mono font-semibold text-text-primary rd-num">{l.price}</span>}
          {l.condition && <span>{l.condition}</span>}
          {l.seller_hash && (
            <span className="inline-flex items-center gap-1" title="Seller usernames are hashed before publishing">
              <RiUserLine className="size-3" aria-hidden />
              <code className="font-mono">{l.seller_hash}</code>
            </span>
          )}
        </p>
        <p className="text-caption-1-regular text-text-secondary">{l.verdict.reason}</p>
        {l.verdict.identifiers_found.length > 0 && (
          <p className="flex flex-wrap items-center gap-1 text-caption-1-regular text-text-tertiary">
            Found:
            {l.verdict.identifiers_found.map((id) => (
              <code key={id} className="rounded border border-caution-border bg-caution-surface px-1 font-mono text-caption-1-medium text-text-primary">
                {id}
              </code>
            ))}
          </p>
        )}
        {l.link && (
          <a href={l.link} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-caption-1-semibold text-ink hover:underline">
            {l.listing_id.includes("placeholder") ? "Search eBay" : "View on eBay"} <RiExternalLinkLine className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </li>
  );
}

function Detail({ r }: { r: ScanByRecall }) {
  const detail = useLoad(() => getScanDetail(r.recall_number), r.recall_number);
  const listings = detail.data?.listings ?? [];
  const order = { match: 0, check: 1, no_match: 2 } as const;
  return (
    <Panel
      className="rd-rise"
      title={shortTitle(r.title)}
      description={
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-mono">#{r.recall_number}</span>
          <span>
            {num(r.listings)} listings · <span className="text-stop-text">{r.match} match</span> · <span className="text-caution-text">{r.check} check</span>
          </span>
          <PlaceholderNote show={!!detail.data?.placeholder}>Placeholder listings</PlaceholderNote>
        </span>
      }
    >
      {detail.loading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-background-secondary-default" />
          ))}
        </div>
      ) : listings.length ? (
        <ul className="flex flex-col gap-2">
          {[...listings]
            .sort((a, b) => order[a.verdict.verdict] - order[b.verdict.verdict])
            .map((l) => (
              <ListingCard key={l.listing_id} l={l} />
            ))}
        </ul>
      ) : (
        <p className="py-6 text-center text-body-2-regular text-text-tertiary">No example listings stored for this recall.</p>
      )}
    </Panel>
  );
}

export function ScanView() {
  const scan = useLoad(getScan, "scan");
  const recalls = useLoad(getRecalls, "recalls");
  const [filter, setFilter] = useState<"flagged" | "kids" | "all">("flagged");
  const [sel, setSel] = useState<string | null>(null);
  const s = scan.data;
  const kidsSet = useMemo(() => new Set((recalls.data ?? []).filter((r) => r.is_childrens).map((r) => r.recall_number)), [recalls.data]);

  const rows = useMemo(() => {
    const list = s?.by_recall ?? [];
    const isKids = (x: ScanByRecall) => x.is_childrens ?? kidsSet.has(x.recall_number);
    return list
      .filter((x) => (filter === "flagged" ? x.match + x.check > 0 : filter === "kids" ? isKids(x) : true))
      .sort((a, b) => b.match - a.match || b.check - a.check || b.listings - a.listings);
  }, [s, filter, kidsSet]);
  const withExamples = rows.find((x) => x.examples.length > 0);
  const selected = rows.find((x) => x.recall_number === sel) ?? withExamples ?? rows[0];
  const maxListings = Math.max(1, ...rows.map((x) => x.listings));

  return (
    <Page wide>
      <header className="rd-ruled mb-6 flex flex-col gap-5 overflow-hidden rounded-3xl border border-border-button-default bg-background-primary-default px-5 py-6 sm:px-8 sm:ps-14 sm:py-8">
        <div className="flex flex-col gap-2">
          <p className="rd-eyebrow text-text-tertiary">SerpApi eBay engine · {s ? `scanned ${formatDate(s.generated_at)}` : "…"}</p>
          <h1 className="rd-notice max-w-[880px] text-[34px] leading-[38px] text-balance text-text-primary sm:text-[48px] sm:leading-[52px]">
            We searched eBay for every product CPSC recalled since July&nbsp;18
          </h1>
          <p className="max-w-[680px] text-body-regular text-text-secondary">
            Reselling a recalled product is illegal in the US. For each recall, we ran the spec&apos;s search queries on eBay, and the fine-tuned 4B model read every listing: <span className="font-semibold text-stop-text">match</span>, <span className="font-semibold text-caution-text">check</span> or no match.
          </p>
          {s?.placeholder && <PlaceholderNote show className="w-fit">{s.note ?? "Placeholder numbers until the real scan lands"}</PlaceholderNote>}
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-5">
          <Big label="Recalls scanned" value={s ? num(s.recalls_scanned) : "…"} sub={s ? `${num(s.searches_spent)} searches` : undefined} />
          <Big label="Listings seen" value={s ? num(s.listings_seen) : "…"} />
          <Big label="Flagged: match" value={s ? num(s.flagged_match) : "…"} tone="stop" sub="model says it is the recalled product" />
          <Big label="Flagged: check" value={s ? num(s.flagged_check) : "…"} tone="caution" sub="label decides it" />
          <Big label="Human-verified matches" value={s ? num(s.human_verified_match) : "…"} tone="ink" sub={s ? `${num(s.childrens_flagged)} children's flags` : undefined} />
        </div>
        <div className="flex items-start gap-3 rounded-xl border border-accent-200 bg-background-secondary-default px-3 py-2.5">
          <RiShieldCheckLine className="mt-0.5 size-4 shrink-0 text-ink" aria-hidden />
          <p className="text-caption-1-regular text-text-secondary">
            <span className="font-semibold text-text-primary">Numbers verified by a human.</span> The model flags; a person opened each flagged listing and confirmed it against the CPSC text. We only quote human-verified matches. Seller names are hashed, and we don&apos;t contact or report sellers.
          </p>
        </div>
      </header>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
        <Panel
          title="Per recall"
          padded={false}
          actions={
            <SegmentedControl aria-label="Filter recalls" selectedKeys={[filter]} onSelectionChange={(k) => setFilter(([...k][0] as typeof filter) ?? "flagged")}>
              <SegmentedControlItem id="flagged">Flagged</SegmentedControlItem>
              <SegmentedControlItem id="kids">Kids</SegmentedControlItem>
              <SegmentedControlItem id="all">All</SegmentedControlItem>
            </SegmentedControl>
          }
        >
          <ul className="flex max-h-[720px] flex-col overflow-y-auto p-1.5" role="listbox" aria-label="Recalls">
            {rows.map((x) => {
              const active = selected?.recall_number === x.recall_number;
              return (
                <li key={x.recall_number} role="option" aria-selected={active}>
                  <button
                    type="button"
                    onClick={() => setSel(x.recall_number)}
                    className={cx(
                      "flex w-full cursor-pointer flex-col gap-1.5 rounded-xl px-3 py-2.5 text-start outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                      active ? "bg-background-secondary-default ring-1 ring-border-button-default" : "hover:bg-background-secondary-default/70",
                    )}
                  >
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate text-body-2-semibold text-text-primary">{shortTitle(x.title)}</span>
                      <span className="shrink-0 font-mono text-caption-1-regular text-text-tertiary">#{x.recall_number}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-background-tertiary-default" aria-hidden>
                        <span className="absolute inset-y-0 start-0 rounded-full bg-chart-5" style={{ width: `${(x.listings / maxListings) * 100}%` }} />
                      </span>
                      <span className="w-[92px] shrink-0 text-end font-mono text-caption-1-medium text-text-secondary rd-num">
                        {num(x.listings)} · <span className={x.match ? "text-stop-text" : ""}>{x.match}</span>/<span className={x.check ? "text-caution-text" : ""}>{x.check}</span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
            {!rows.length && <li className="px-3 py-8 text-center text-body-2-regular text-text-tertiary">{scan.loading ? "Loading…" : "Nothing here."}</li>}
          </ul>
        </Panel>
        {selected && <Detail key={selected.recall_number} r={selected} />}
      </div>
    </Page>
  );
}

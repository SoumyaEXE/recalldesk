"use client";

import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";
import {
  RiArrowDownSLine,
  RiErrorWarningLine,
  RiExternalLinkLine,
  RiEyeLine,
  RiImageLine,
  RiSearch2Line,
  RiShieldCheckLine,
  RiShoppingBag3Line,
  RiUserLine,
} from "@remixicon/react";
import { Pagination } from "@/components/base/pagination/pagination";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Card, ChildrensPill, DemoBadge, EmptyState, IconTile, IdChip, Pill, SkeletonRows, VerdictPill } from "@/components/ui/surface";
import { FilterPill, RowAvatar, RowTitle, SearchField, Toolbar } from "@/components/ui/table";
import { getRecalls, getScan, getScanDetail } from "@/lib/api";
import { formatDate, num, shortTitle } from "@/lib/format";
import type { RecallRecord, ScanByRecall, ScannedListing } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

function ListingCard({ l }: { l: ScannedListing }) {
  const [failed, setFailed] = useState(false);
  return (
    <li className="flex min-w-0 gap-3 rounded-xl border border-line bg-card p-3 shadow-card">
      <span className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-subtle">
        {l.thumbnail && !failed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={l.thumbnail} alt="" width={80} height={80} onError={() => setFailed(true)} className="size-full object-cover" />
        ) : (
          <RiImageLine className="size-6 text-foreground-icon-quaternary" aria-label="No photo" />
        )}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <VerdictPill verdict={l.verdict.verdict} size="sm" />
          {l.human_verified && (
            <Pill size="sm" tone="blue" icon={RiShieldCheckLine}>
              Human-verified
            </Pill>
          )}
        </div>
        <p className="line-clamp-2 text-body-2-semibold break-words text-text-primary">{l.title}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption-1-regular text-text-tertiary">
          {l.price && <span className="text-body-2-semibold text-text-primary tabular-nums">{l.price}</span>}
          {l.condition && <span>{l.condition}</span>}
          {l.seller_hash && (
            <span className="inline-flex items-center gap-1" title="Seller usernames are hashed before publishing">
              <RiUserLine className="size-3" aria-hidden />
              <code className="rd-mono">{l.seller_hash}</code>
            </span>
          )}
        </p>
        <p className="line-clamp-2 text-caption-1-regular text-text-secondary">{l.verdict.reason}</p>
        {l.verdict.identifiers_found.length > 0 && (
          <p className="flex flex-wrap items-center gap-1">
            {l.verdict.identifiers_found.map((id) => (
              <IdChip key={id}>{id}</IdChip>
            ))}
          </p>
        )}
        {l.link && (
          <a href={l.link} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
            {l.listing_id.includes("placeholder") ? "Search eBay" : "View on eBay"} <RiExternalLinkLine className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </li>
  );
}

function Listings({ r }: { r: ScanByRecall }) {
  const detail = useLoad(() => getScanDetail(r.recall_number), `scan-${r.recall_number}`);
  const order = { match: 0, check: 1, no_match: 2 } as const;
  const listings = [...(detail.data?.listings ?? [])].sort((a, b) => order[a.verdict.verdict] - order[b.verdict.verdict]);
  if (detail.loading) return <SkeletonRows rows={2} />;
  if (!listings.length)
    return (
      <EmptyState icon={RiSearch2Line} title="No listings stored for this recall" className="py-8">
        {r.listings ? `${num(r.listings)} listings were seen; example listings weren't kept for this one.` : "The eBay scan hasn't stored listings for this recall yet. Results land here after the next SerpApi run."}
      </EmptyState>
    );
  return (
    <div className="flex flex-col gap-3 p-4">
      {detail.placeholder && <DemoBadge>Placeholder listings</DemoBadge>}
      <ul className="grid gap-3 lg:grid-cols-2">
        {listings.map((l) => (
          <ListingCard key={l.listing_id} l={l} />
        ))}
      </ul>
    </div>
  );
}

function RecallRow({ r, rec, open, onToggle }: { r: ScanByRecall & { kids: boolean }; rec?: RecallRecord; open: boolean; onToggle: () => void }) {
  const reduce = useReducedMotion();
  const id = `scan-${r.recall_number}`;
  const flagged = r.match + r.check;
  return (
    <li className={cx("border-b border-line last:border-b-0", open && "bg-subtle")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
        className="grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-3 text-start outline-none transition-colors hover:bg-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring focus-visible:ring-inset sm:px-5 md:min-h-16 md:grid-cols-[minmax(0,1fr)_110px_90px_90px_120px_28px]"
      >
        <RowTitle
          leading={<RowAvatar label={rec?.spec?.brand ?? r.title} src={rec?.images[0]} icon={RiShoppingBag3Line} />}
          title={shortTitle(r.title)}
          sub={
            <>
              <span className="rd-mono">#{r.recall_number}</span>
              {rec && ` · ${formatDate(rec.recall_date, { month: "short", day: "numeric" })}`}
            </>
          }
        />
        <RiArrowDownSLine className={cx("size-5 text-foreground-icon-tertiary transition-transform md:hidden", open && "rotate-180")} aria-hidden />
        <span className="col-span-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-caption-1-regular text-text-tertiary md:hidden">
          <span>
            <span className="font-semibold text-text-primary tabular-nums">{num(r.listings)}</span> listings
          </span>
          <span>
            <span className="font-semibold text-stop-text tabular-nums">{r.match}</span> match
          </span>
          <span>
            <span className="font-semibold text-caution-text tabular-nums">{r.check}</span> check
          </span>
          {r.kids && <ChildrensPill size="sm" />}
        </span>
        <span className="hidden text-end text-body-2-medium text-text-primary tabular-nums md:block">{num(r.listings)}</span>
        <span className={cx("hidden text-end text-body-2-semibold tabular-nums md:block", r.match ? "text-stop-text" : "text-text-tertiary")}>{r.match}</span>
        <span className={cx("hidden text-end text-body-2-semibold tabular-nums md:block", r.check ? "text-caution-text" : "text-text-tertiary")}>{r.check}</span>
        <span className="hidden justify-end md:flex">{flagged ? <Pill size="sm" tone="red" dot>{flagged} flagged</Pill> : r.kids ? <ChildrensPill size="sm" /> : <Pill size="sm">None</Pill>}</span>
        <RiArrowDownSLine className={cx("hidden size-5 justify-self-end text-foreground-icon-tertiary transition-transform md:block", open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={id}
            key="body"
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden border-t border-line"
          >
            <Listings r={r} />
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

const PAGE = 12;

export function EbayView() {
  const scan = useLoad(getScan, "scan");
  const recalls = useLoad(getRecalls, "recalls");
  const params = useSearchParams();
  const s = scan.data;
  const byNumber = useMemo(() => new Map((recalls.data ?? []).map((r) => [r.recall_number, r])), [recalls.data]);
  const anyFlagged = (s?.by_recall ?? []).some((x) => x.match + x.check > 0);
  const [filter, setFilter] = useState<"auto" | "flagged" | "kids" | "all">("auto");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(params.get("open"));
  const [page, setPage] = useState(1);
  const f = filter === "auto" ? (anyFlagged ? "flagged" : "all") : filter;

  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (s?.by_recall ?? [])
      .map((x) => ({ ...x, kids: x.is_childrens ?? byNumber.get(x.recall_number)?.is_childrens ?? false }))
      .filter((x) => (f === "flagged" ? x.match + x.check > 0 : f === "kids" ? x.kids : true))
      .filter((x) => !t || `${x.title} ${x.recall_number}`.toLowerCase().includes(t))
      .sort((a, b) => b.match - a.match || b.check - a.check || b.listings - a.listings || (byNumber.get(b.recall_number)?.recall_date ?? "").localeCompare(byNumber.get(a.recall_number)?.recall_date ?? ""));
  }, [s, f, q, byNumber]);

  // Deep link: put the opened recall on the first page.
  const openRow = open ? rows.find((x) => x.recall_number === open) : undefined;
  const ordered = openRow && params.get("open") === open ? [openRow, ...rows.filter((x) => x !== openRow)] : rows;
  const totalPages = Math.max(1, Math.ceil(ordered.length / PAGE));
  const current = Math.min(page, totalPages);
  const visible = ordered.slice((current - 1) * PAGE, current * PAGE);
  const flagged = s ? s.flagged_match + s.flagged_check : null;

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              SerpApi eBay engine
            </Pill>
            {s && <span className="text-caption-1-regular text-text-tertiary">Scanned {formatDate(s.generated_at)}</span>}
            <DemoBadge show={scan.placeholder}>Placeholder until the real scan lands</DemoBadge>
          </>
        }
        title="eBay monitor"
        description="Reselling a recalled product is illegal in the US. For every recall since July 18 we ran the spec's search queries on eBay, and the fine-tuned 4B model read each listing: match, check, or no match."
      />

      <KpiRow className="mb-5">
        <KpiCard index={0} icon={RiSearch2Line} tone="gray" label="Searches spent" value={s?.searches_spent ?? null} loading={scan.loading} status={s ? `${num(s.recalls_scanned)} recalls` : undefined} caption="Every response cached; none re-spent" />
        <KpiCard index={1} icon={RiEyeLine} tone="blue" label="Listings seen" value={s?.listings_seen ?? null} loading={scan.loading} status="Read by the 4B" caption="Titles, condition, item specifics" />
        <KpiCard index={2} icon={RiErrorWarningLine} tone="red" label="Flagged" value={flagged} loading={scan.loading} status="Model" caption={s ? `${num(s.flagged_match)} match · ${num(s.flagged_check)} check` : undefined} />
        <KpiCard index={3} icon={RiShieldCheckLine} tone="green" label="Human-verified matches" value={s?.human_verified_match ?? null} loading={scan.loading} status="Quoted" caption={s ? `${num(s.childrens_flagged)} children's flags` : undefined} />
      </KpiRow>

      <div className="mb-5 flex items-start gap-3 rounded-xl border border-info-border bg-info-surface px-4 py-3">
        <IconTile icon={RiShieldCheckLine} tone="blue" size="sm" className="bg-card" />
        <p className="pt-1 text-body-2-regular text-text-secondary">
          <span className="font-semibold text-text-primary">Numbers verified by a human.</span> The model flags; a person opened each flagged listing and confirmed it against the CPSC text. We only quote human-verified matches. Seller names are hashed, and we don&apos;t contact or report sellers.
          {s?.placeholder && s.note && <span className="mt-1 block text-caption-1-regular text-caution-text">{s.note}</span>}
        </p>
      </div>

      <Card>
        <Toolbar>
          <SearchField value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Recall # or product" label="Search scanned recalls" className="md:max-w-[320px] md:flex-1" />
          <FilterPill
            label="Show"
            value={f}
            onChange={(v) => {
              setFilter(v);
              setPage(1);
            }}
            options={[
              { value: "flagged", label: "Flagged", count: (s?.by_recall ?? []).filter((x) => x.match + x.check > 0).length },
              { value: "kids", label: "Children's" },
              { value: "all", label: "All recalls", count: s?.by_recall.length },
            ]}
          />
        </Toolbar>
        <div className="hidden h-10 grid-cols-[minmax(0,1fr)_110px_90px_90px_120px_28px] items-center gap-x-4 border-b border-line bg-subtle px-5 text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase md:grid" aria-hidden>
          <span>Recall</span>
          <span className="text-end">Listings</span>
          <span className="text-end">Match</span>
          <span className="text-end">Check</span>
          <span className="text-end">Status</span>
          <span />
        </div>
        {scan.loading ? (
          <SkeletonRows rows={6} />
        ) : visible.length ? (
          <ul aria-label="Scanned recalls">
            {visible.map((x) => (
              <RecallRow key={x.recall_number} r={x} rec={byNumber.get(x.recall_number)} open={open === x.recall_number} onToggle={() => setOpen(open === x.recall_number ? null : x.recall_number)} />
            ))}
          </ul>
        ) : (
          <EmptyState icon={RiShoppingBag3Line} title="Nothing flagged here">
            Try “All recalls”.
          </EmptyState>
        )}
        {totalPages > 1 && (
          <div className="flex flex-col gap-3 border-t border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <p className="text-caption-1-regular whitespace-nowrap text-text-tertiary tabular-nums">
              Showing {(current - 1) * PAGE + 1}–{Math.min(current * PAGE, ordered.length)} of {ordered.length}
            </p>
            <Pagination page={current} totalPages={totalPages} onChange={setPage} aria-label="Scanned recalls pages" />
          </div>
        )}
      </Card>
    </Page>
  );
}

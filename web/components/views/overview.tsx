"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  RiAddCircleFill,
  RiAlarmWarningLine,
  RiArchiveStackLine,
  RiArrowRightLine,
  RiArrowRightUpLine,
  RiBrainLine,
  RiCalendarScheduleLine,
  RiCheckboxCircleLine,
  RiErrorWarningLine,
  RiFileList3Line,
  RiNodeTree,
  RiPrinterLine,
  RiShieldFlashLine,
  RiShoppingBag3Line,
} from "@remixicon/react";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { ItemDrawer, type FlaggedItem } from "@/components/rd/item-drawer";
import { NavButton } from "@/components/rd/nav-button";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Card, CardHeader, ChildrensPill, DemoBadge, Dot, EmptyState, IconTile, Pill, Skeleton, VerdictPill, type Icon, type Tone } from "@/components/ui/surface";
import { DataTable, RowAvatar, RowTitle, type Column } from "@/components/ui/table";
import { getInventory, getLatestCard, getMemories, getRecalls, getRuns, getScan } from "@/lib/api";
import { joinInventory } from "@/lib/inventory";
import { formatDate, num, relativeTime, shortTitle } from "@/lib/format";
import { countdown, formatSweep, nextSweep } from "@/lib/schedule";
import { useShop } from "@/lib/shop";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

function useNow(ms = 1000) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const t = window.setInterval(tick, ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

function NextSweepCard() {
  const now = useNow();
  const at = now ? nextSweep(now) : null;
  const c = at && now ? countdown(at, now) : null;
  const units: [string, number | undefined][] = [
    ["days", c?.d],
    ["hrs", c?.h],
    ["min", c?.m],
    ["sec", c?.s],
  ];
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Next sweep"
        icon={RiCalendarScheduleLine}
        description={at ? formatSweep(at) : "Thursday · 2:00 PM ET"}
        actions={
          <Pill tone="green" dot size="sm">
            Scheduled
          </Pill>
        }
      />
      <div className="px-5 pb-4">
        <div className="grid grid-cols-4 gap-2" role="timer" aria-label={c ? `${c.d} days ${c.h} hours ${c.m} minutes until the next sweep` : "Countdown"}>
          {units.map(([u, v]) => (
            <div key={u} className="flex flex-col items-center rounded-lg border border-line bg-subtle py-2.5">
              <span className="text-title-2-semibold text-text-primary tabular-nums">{v === undefined ? "–" : String(v).padStart(2, "0")}</span>
              <span className="text-caption-2-medium text-text-tertiary">{u}</span>
            </div>
          ))}
        </div>
        <ol className="mt-4 flex flex-col gap-2" aria-label="What runs">
          {["fetch_new_recalls", "extract_spec", "check_items", "scan_ebay_store", "compose_card"].map((s, i) => (
            <li key={s} className="flex items-center gap-2.5 text-caption-1-regular text-text-secondary">
              <span className="flex size-5 items-center justify-center rounded-full bg-subtle text-caption-2-semibold text-text-tertiary ring-1 ring-line ring-inset tabular-nums">{i + 1}</span>
              <code className="rd-mono text-text-primary">{s}</code>
            </li>
          ))}
        </ol>
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line bg-subtle px-5 py-2.5">
        <span className="truncate text-caption-1-regular text-text-tertiary">
          Temporal schedule · <code className="rd-mono">WeeklyRecallSweep</code>
        </span>
        <Link href="/runs" className="inline-flex shrink-0 items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
          Runs <RiArrowRightLine className="size-3.5" aria-hidden />
        </Link>
      </div>
    </Card>
  );
}

interface Activity {
  id: string;
  at: string;
  icon: Icon;
  tone: Tone;
  title: React.ReactNode;
  sub?: React.ReactNode;
}

export function OverviewView() {
  const shop = useShop();
  const card = useLoad(() => getLatestCard(shop.id), `card-${shop.id}`);
  const recalls = useLoad(getRecalls, "recalls");
  const scan = useLoad(getScan, "scan");
  const runs = useLoad(getRuns, "runs");
  const memories = useLoad(() => getMemories(shop.id), `mem-${shop.id}`);
  const inventory = useLoad(() => getInventory(shop.id), `inv-${shop.id}`);
  const [open, setOpen] = useState<FlaggedItem | null>(null);
  const c = card.data?.card;

  const all = useMemo(() => recalls.data ?? [], [recalls.data]);
  const byNumber = useMemo(() => new Map(all.map((r) => [r.recall_number, r])), [all]);
  const latest = all.reduce((m, r) => (r.recall_date > m ? r.recall_date : m), "");
  const week = all.filter((r) => r.recall_date === latest);
  const kids = week.filter((r) => r.is_childrens).length;

  const flagged = useMemo(() => joinInventory(inventory.data ?? [], c).flags, [inventory.data, c]);

  const activity = useMemo<Activity[]>(() => {
    const out: Activity[] = [];
    for (const r of runs.data ?? []) {
      if (r.shop_id && r.shop_id !== shop.id && r.shop_id !== "demo-shop") continue;
      out.push({
        id: `run-${r.workflow_id}`,
        at: r.ended_at ?? r.started_at ?? "",
        icon: RiNodeTree,
        tone: r.resumed_after_crash ? "violet" : r.status === "completed" ? "green" : "blue",
        title: (
          <>
            <code className="rd-mono">{r.workflow_type ?? "Workflow"}</code> {r.status === "completed" ? "completed" : r.status}
          </>
        ),
        sub: r.resumed_after_crash ? "Worker killed mid-run · resumed on a fresh worker, no activity ran twice" : (r.retries ?? 0) > 0 ? `${r.retries} activity retr${r.retries === 1 ? "y" : "ies"}` : r.workflow_id,
      });
    }
    for (const m of memories.data ?? []) {
      if (!m.created_at) continue;
      out.push({ id: `mem-${m.memory_id}`, at: m.created_at, icon: RiBrainLine, tone: "blue", title: "Shop memory saved", sub: m.text.replace(/^Shop correction: /, "").replace(/\s*\[recall=.*\]$/, "") });
    }
    for (const r of all.filter((x) => x.recall_date >= latest && latest).slice(0, 4)) {
      out.push({ id: `rec-${r.recall_number}`, at: `${r.recall_date}T18:00:00Z`, icon: RiShieldFlashLine, tone: r.is_childrens ? "blue" : "gray", title: <>CPSC posted #{r.recall_number}</>, sub: shortTitle(r.title) });
    }
    return out.filter((a) => a.at).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 7);
  }, [runs.data, memories.data, all, latest, shop.id]);

  const columns: Column<FlaggedItem>[] = [
    {
      id: "item",
      header: "Item",
      mobile: "primary",
      width: "38%",
      sort: (r) => r.label,
      cell: (r) => <RowTitle leading={<RowAvatar label={r.label} tone={r.verdict === "match" ? "red" : "amber"} src={byNumber.get(r.recall_number)?.images[0]} />} title={r.label} sub={r.recall_title ? shortTitle(r.recall_title) : undefined} />,
    },
    { id: "status", header: "Status", mobile: "badge", width: "16%", sort: (r) => r.verdict, cell: (r) => <VerdictPill verdict={r.verdict} /> },
    { id: "recall", header: "Recall #", mobile: "meta", width: "12%", sort: (r) => r.recall_number, cell: (r) => <span className="rd-mono text-body-2-medium text-text-primary">#{r.recall_number}</span> },
    {
      id: "what",
      header: "Why / where to look",
      mobile: "meta",
      mobileLabel: "Why",
      cell: (r) => <span className="line-clamp-2 text-caption-1-regular text-text-secondary">{r.verdict === "match" ? r.why : r.look_for ?? "Brand and model on the label"}</span>,
    },
  ];

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill tone="blue" dot size="sm">
              Week of {c ? formatDate(c.week_of, { month: "short", day: "numeric" }) : "…"}
            </Pill>
            <DemoBadge show={card.placeholder}>Demo data</DemoBadge>
          </>
        }
        title="Overview"
        description={`CPSC posted ${week.length || "its"} recalls on Thursday. RecallDesk re-checked ${shop.short}'s inventory against them. Pull what's flagged, check the labels, print the card.`}
        actions={
          <>
            <NavButton href="/cards" variant="secondary" leadingIcon={RiPrinterLine}>
              Open printable card
            </NavButton>
            <NavButton href="/inventory?new=1" leadingIcon={RiAddCircleFill}>
              Check new items
            </NavButton>
          </>
        }
      />

      <KpiRow className="mb-6">
        <KpiCard index={0} icon={RiAlarmWarningLine} tone="blue" label="New recalls this Thursday" value={c?.new_recalls ?? (week.length || null)} loading={card.loading && recalls.loading} status={latest ? formatDate(latest, { weekday: "short", month: "short", day: "numeric" }) : "Thursday"} caption={`${kids} for children · ${all.length || "…"} since Jul 18`} />
        <KpiCard index={1} icon={RiArchiveStackLine} tone="green" label="Items checked" value={c?.items_checked} loading={card.loading} status="Checked" caption={c ? `Re-checked ${relativeTime(c.generated_at)}` : "Your inventory list"} />
        <KpiCard index={2} icon={RiErrorWarningLine} tone="red" label="Do not sell" value={c?.do_not_sell.length} loading={card.loading} status="Pull now" caption="Pull from the floor and listings" />
        <KpiCard index={3} icon={RiCheckboxCircleLine} tone="amber" label="Check label" value={c?.check_label.length} loading={card.loading} status="Look first" caption="The label decides it" />
      </KpiRow>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Card>
            <CardHeader
              title="This week's card"
              description={c ? <span>Everything flagged for {shop.short} · <code className="rd-mono">{c.id}</code></span> : "Loading…"}
              actions={
                <NavButton href="/cards" size="small" variant="secondary" trailingIcon={RiArrowRightUpLine}>
                  Printable card
                </NavButton>
              }
            />
            <div className="border-t border-line">
              <DataTable
                caption="Flagged items this week"
                rows={flagged}
                columns={columns}
                rowKey={(r) => `${r.verdict}-${r.recall_number}-${r.label}`}
                rowLabel={(r) => `Open ${r.label}`}
                onRowOpen={setOpen}
                loading={card.loading}
                pageSize={6}
                empty={
                  <EmptyState icon={RiCheckboxCircleLine} tone="green" title="All clear this week">
                    None of the items checked match a recall. Keep the label photos anyway.
                  </EmptyState>
                }
              />
            </div>
          </Card>

          <Card>
            <CardHeader title="Activity" description="Workflow runs, shop memories and new CPSC postings" />
            <ol className="flex flex-col px-5 pb-4" aria-label="Recent activity">
              {runs.loading || memories.loading
                ? Array.from({ length: 4 }, (_, i) => (
                    <li key={i} className="flex items-center gap-3 py-2.5">
                      <Skeleton className="size-8 rounded-lg" />
                      <Skeleton className="h-3 flex-1" />
                    </li>
                  ))
                : activity.map((a, i) => (
                    <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
                      {i < activity.length - 1 && <span className="absolute start-4 top-9 bottom-0 w-px bg-line" aria-hidden />}
                      <IconTile icon={a.icon} tone={a.tone} size="sm" />
                      <div className="flex min-w-0 flex-1 flex-col gap-0.5 pt-1">
                        <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-body-2-medium text-text-primary">
                          <span>{a.title}</span>
                          <span className="text-caption-1-regular text-text-tertiary">{relativeTime(a.at)}</span>
                        </p>
                        {a.sub && <p className="line-clamp-2 text-caption-1-regular break-words text-text-tertiary">{a.sub}</p>}
                      </div>
                    </li>
                  ))}
            </ol>
          </Card>
        </div>

        <aside className="flex min-w-0 flex-col gap-5" aria-label="This week">
          <NextSweepCard />

          <Card>
            <CardHeader title="Posted this Thursday" description={latest ? formatDate(latest, { weekday: "long", month: "short", day: "numeric" }) : "…"} actions={<span className="text-caption-1-semibold text-text-tertiary tabular-nums">{week.length}</span>} />
            <ul className="flex flex-col border-t border-line">
              {recalls.loading
                ? Array.from({ length: 4 }, (_, i) => (
                    <li key={i} className="flex flex-col gap-2 border-b border-line px-5 py-3 last:border-b-0">
                      <Skeleton className="h-3 w-3/4" />
                      <Skeleton className="h-2.5 w-1/3" />
                    </li>
                  ))
                : week.slice(0, 6).map((r) => (
                    <li key={r.recall_number} className="border-b border-line last:border-b-0">
                      <Link href={`/recalls?open=${r.recall_number}`} className="flex flex-col gap-1 px-5 py-3 outline-none transition-colors hover:bg-hover focus-visible:bg-hover">
                        <span className="flex items-center gap-2">
                          <span className="rd-mono text-caption-1-medium text-text-tertiary">#{r.recall_number}</span>
                          {r.is_childrens && <ChildrensPill size="sm" />}
                        </span>
                        <span className="text-body-2-semibold text-text-primary">{shortTitle(r.title)}</span>
                        <span className="line-clamp-1 text-caption-1-regular text-text-tertiary">{r.spec?.hazard_short ?? r.hazards[0]}</span>
                      </Link>
                    </li>
                  ))}
            </ul>
            <div className="border-t border-line px-5 py-2.5">
              <Link href="/recalls" className="inline-flex items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
                All {all.length || ""} recalls <RiArrowRightLine className="size-3.5" aria-hidden />
              </Link>
            </div>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader title="eBay monitor" icon={RiShoppingBag3Line} description="Every recall since Jul 18, searched on eBay" actions={<DemoBadge show={scan.placeholder} />} />
            <div className="grid grid-cols-3 gap-px border-t border-line bg-line">
              {[
                ["Listings", scan.data?.listings_seen, "text-text-primary"],
                ["Match", scan.data?.flagged_match, "text-stop-text"],
                ["Check", scan.data?.flagged_check, "text-caution-text"],
              ].map(([k, v, cls]) => (
                <div key={k as string} className="flex flex-col gap-0.5 bg-card px-4 py-3">
                  <span className="text-caption-1-medium text-text-tertiary">{k as string}</span>
                  <span className={cx("text-title-2-semibold tabular-nums", cls as string)}>{v === undefined ? "…" : num(v as number)}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between gap-2 border-t border-line bg-subtle px-5 py-2.5">
              <span className="flex items-center gap-1.5 text-caption-1-regular text-text-tertiary">
                <Dot tone={scan.placeholder ? "amber" : "green"} /> {scan.placeholder ? "Scan pending · placeholder" : "Human-verified numbers"}
              </span>
              <Link href="/ebay" className="inline-flex items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
                Open <RiArrowRightLine className="size-3.5" aria-hidden />
              </Link>
            </div>
          </Card>

          <Card className="flex items-center gap-3 p-4">
            <IconTile icon={RiFileList3Line} tone="gray" />
            <div className="min-w-0 flex-1">
              <p className="text-body-2-semibold text-text-primary">Print it for the intake desk</p>
              <p className="text-caption-1-regular text-text-tertiary">One Letter page with a sign-off line.</p>
            </div>
            <NavButton href="/cards" size="small" variant="secondary">
              Open
            </NavButton>
          </Card>
        </aside>
      </div>

      <ItemDrawer item={open} recall={open ? byNumber.get(open.recall_number) : undefined} shopId={shop.id} onClose={() => setOpen(null)} />
    </Page>
  );
}

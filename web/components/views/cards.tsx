"use client";

import { useMemo, useState } from "react";
import { RiCalendarCheckLine, RiFileList3Line, RiPrinterLine, RiRestartLine, RiTimeLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { RecallCard } from "@/components/rd/recall-card";
import { Card, CardHeader, DemoBadge, EmptyState, IconTile, Pill, Skeleton } from "@/components/ui/surface";
import { getCardStatus, getLatestCard, getRuns, isSimulated } from "@/lib/api";
import { formatDate, relativeTime } from "@/lib/format";
import { useShop } from "@/lib/shop";
import type { RecallCard as Card_ } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

interface Entry {
  key: string;
  title: string;
  sub: string;
  workflowId?: string;
  latest: boolean;
  at?: string | null;
  resumed?: boolean;
  simulated?: boolean;
}

export function CardsView() {
  const shop = useShop();
  const latest = useLoad(() => getLatestCard(shop.id), `card-${shop.id}`);
  const runs = useLoad(getRuns, "runs");
  const [sel, setSel] = useState<string>("latest");
  const entry = sel === "latest" ? null : sel;
  const picked = useLoad(() => (entry ? getCardStatus(entry) : getLatestCard(shop.id)), `pick-${shop.id}-${entry ?? "latest"}`);
  const card: Card_ | undefined = (entry ? picked.data?.card : latest.data?.card) ?? latest.data?.card;

  const entries = useMemo<Entry[]>(() => {
    const c = latest.data?.card;
    const out: Entry[] = [];
    if (c) out.push({ key: "latest", title: `Week of ${formatDate(c.week_of, { month: "long", day: "numeric" })}`, sub: `${c.do_not_sell.length} do not sell · ${c.check_label.length} check label`, workflowId: c.workflow_id, latest: true, at: c.generated_at });
    for (const r of runs.data ?? []) {
      if (r.status !== "completed" || (r.shop_id && r.shop_id !== shop.id && !(shop.id === "little-loop" && r.shop_id === "demo-shop"))) continue;
      if (r.workflow_id === c?.workflow_id) continue;
      out.push({ key: r.workflow_id, title: r.workflow_type === "WeeklyRecallSweep" ? "Weekly sweep" : "On-demand check", sub: r.workflow_id, workflowId: r.workflow_id, latest: false, at: r.ended_at ?? r.started_at, resumed: r.resumed_after_crash, simulated: isSimulated(r.workflow_id) });
    }
    return out;
  }, [latest.data, runs.data, shop.id]);

  const loading = latest.loading || (!!entry && picked.loading);

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Printable notice
            </Pill>
            <DemoBadge show={latest.placeholder}>Demo data</DemoBadge>
          </>
        }
        title="Weekly cards"
        description="One card per week for the intake desk: DO NOT SELL and CHECK LABEL, with exactly where to look. Prints on one Letter page with a sign-off line."
        actions={
          <Button leadingIcon={RiPrinterLine} onClick={() => window.print()} disabled={!card}>
            Print card
          </Button>
        }
      />

      <div className="grid items-start gap-5 print:block lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card as="aside" aria-label="Card history" className="rd-no-print lg:sticky lg:top-6">
          <CardHeader title="Card history" description={shop.short} icon={RiFileList3Line} />
          <ul className="flex flex-col gap-1 border-t border-line p-2">
            {latest.loading
              ? Array.from({ length: 3 }, (_, i) => (
                  <li key={i} className="flex flex-col gap-2 p-3">
                    <Skeleton className="h-3 w-3/4" />
                    <Skeleton className="h-2.5 w-1/2" />
                  </li>
                ))
              : entries.map((e) => {
                  const active = sel === e.key;
                  return (
                    <li key={e.key}>
                      <button
                        type="button"
                        aria-pressed={active}
                        onClick={() => setSel(e.key)}
                        className={cx("flex w-full cursor-pointer items-start gap-3 rounded-lg p-2.5 text-start outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring", active ? "bg-active-nav" : "hover:bg-hover")}
                      >
                        <IconTile icon={e.latest ? RiCalendarCheckLine : e.resumed ? RiRestartLine : RiTimeLine} tone={e.latest ? "blue" : e.resumed ? "violet" : "gray"} size="sm" />
                        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <span className="flex items-center gap-1.5">
                            <span className="truncate text-body-2-semibold text-text-primary">{e.title}</span>
                            {e.latest && <Pill size="sm" tone="green">Current</Pill>}
                            {e.simulated && <Pill size="sm">Sim</Pill>}
                          </span>
                          <span className={cx("truncate text-caption-1-regular text-text-tertiary", !e.latest && "rd-mono")}>{e.sub}</span>
                          {e.at && <span className="text-caption-2-regular text-text-tertiary">{relativeTime(e.at)}</span>}
                        </span>
                      </button>
                    </li>
                  );
                })}
          </ul>
          <p className="border-t border-line px-5 py-3 text-caption-1-regular text-text-tertiary">A new card lands here every Thursday after CPSC posts, and after every on-demand check.</p>
        </Card>

        <div className="flex min-w-0 flex-col gap-3">
          {loading ? (
            <Skeleton className="h-[720px] rounded-2xl" />
          ) : card ? (
            <>
              <div className="rd-no-print flex flex-wrap items-center justify-between gap-2 text-caption-1-regular text-text-tertiary">
                <span>
                  Generated {formatDate(card.generated_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · model <code className="rd-mono text-text-secondary">{card.model}</code>
                </span>
                <span>Corrections you make on the card become shop memories.</span>
              </div>
              <RecallCard card={card} correctable className="rd-rise" />
            </>
          ) : (
            <Card>
              <EmptyState icon={RiFileList3Line} title="No card yet">
                Check your items to make this week&apos;s card.
              </EmptyState>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );
}

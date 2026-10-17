"use client";

import { useMemo } from "react";
import { RiArrowRightLine, RiPrinterLine, RiStackLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader, Panel, Stat } from "@/components/rd/app-shell";
import { NavButton } from "@/components/rd/nav-button";
import { RecallCard } from "@/components/rd/recall-card";
import { StepTimeline } from "@/components/rd/step-timeline";
import { getLatestCard, getRecalls, getScan } from "@/lib/api";
import { formatDate, num, shortTitle } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

export function HomeView() {
  const card = useLoad(getLatestCard, "latest-card");
  const recalls = useLoad(getRecalls, "recalls");
  const scan = useLoad(getScan, "scan");
  const c = card.data?.card;

  const week = useMemo(() => {
    const list = recalls.data ?? [];
    const latest = c?.week_of ?? list.reduce((m, r) => (r.recall_date > m ? r.recall_date : m), "");
    return list.filter((r) => r.recall_date === latest);
  }, [recalls.data, c?.week_of]);

  return (
    <Page wide>
      <PageHeader
        eyebrow={c ? `Week of ${formatDate(c.week_of)}` : "This week"}
        title="This week at the intake desk"
        description="CPSC posted its Thursday recalls. We matched them against your inventory. Print the card, pin it by the intake desk, and pull what's on it."
        actions={
          <>
            <NavButton href="/check" variant="secondary" leadingIcon={RiStackLine}>
              Check new items
            </NavButton>
            <Button leadingIcon={RiPrinterLine} onClick={() => window.print()} disabled={!c}>
              Print card
            </Button>
          </>
        }
      />

      <div className="rd-no-print mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="New CPSC recalls" value={c ? c.new_recalls : "…"} hint={week.length ? `${week.filter((r) => r.is_childrens).length} for kids` : undefined} />
        <Stat label="Items checked" value={c ? c.items_checked : "…"} hint="Your inventory list" />
        <Stat label="Do not sell" value={c ? c.do_not_sell.length : "…"} tone="stop" hint="Pull from the floor" />
        <Stat label="Check label" value={c ? c.check_label.length : "…"} tone="caution" hint="Look before listing" />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {card.loading ? (
            <div className="h-[640px] animate-pulse rounded-2xl bg-background-secondary-default" />
          ) : c ? (
            <RecallCard card={c} correctable className="rd-rise" />
          ) : (
            <div className="rd-ruled rounded-2xl border border-dashed border-border-button-hover px-6 py-16 text-center">
              <p className="rd-notice text-[24px] text-text-primary">No card yet</p>
              <p className="mt-1 text-body-2-regular text-text-secondary">Check your items to make this week&apos;s card.</p>
            </div>
          )}
        </div>

        <aside className="rd-no-print flex min-w-0 flex-col gap-4">
          <Panel title="Posted this Thursday" description={week[0] ? formatDate(week[0].recall_date, { weekday: "long", month: "short", day: "numeric" }) : undefined} padded={false}>
            <ul className="divide-y divide-separator-border">
              {week.map((r) => (
                <li key={r.recall_number} className="flex flex-col gap-0.5 px-4 py-2.5">
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-caption-1-semibold text-text-tertiary">#{r.recall_number}</span>
                    {r.is_childrens && <span className="rounded bg-status-blue-background px-1 text-caption-2-semibold text-status-blue-text">Kids</span>}
                  </span>
                  <span className="text-body-2-medium text-text-primary">{shortTitle(r.title)}</span>
                  <span className="text-caption-1-regular text-text-tertiary">{r.spec?.hazard_short}</span>
                </li>
              ))}
              {!week.length && <li className="px-4 py-6 text-body-2-regular text-text-tertiary">Loading…</li>}
            </ul>
            <div className="border-t border-separator-border px-4 py-2.5">
              <NavButton href="/recalls" size="small" variant="ghost" trailingIcon={RiArrowRightLine}>
                All recalls
              </NavButton>
            </div>
          </Panel>

          {scan.data && (
            <Panel title="Meanwhile on eBay" padded>
              <p className="text-body-2-regular text-text-secondary">
                We searched eBay for every product CPSC recalled since July 18 and flagged{" "}
                <span className="font-semibold text-stop-text">{num(scan.data.flagged_match)} likely matches</span> and{" "}
                <span className="font-semibold text-caution-text">{num(scan.data.flagged_check)} to check</span> across {num(scan.data.listings_seen)} listings.
              </p>
              <NavButton href="/scan" size="small" variant="secondary" trailingIcon={RiArrowRightLine} className="mt-3">
                See the scan
              </NavButton>
            </Panel>
          )}

          {card.data?.steps?.length ? (
            <Panel title="How this card was made" description={<span className="font-mono text-caption-1-regular break-all">{card.data.workflow_id ?? c?.workflow_id}</span>}>
              <StepTimeline steps={card.data.steps} dense />
            </Panel>
          ) : null}
        </aside>
      </div>
    </Page>
  );
}

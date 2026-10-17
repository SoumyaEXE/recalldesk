"use client";

import { useState } from "react";
import { RiBankCardLine, RiDownload2Line, RiExchangeDollarLine, RiFileTextLine, RiLockLine, RiShieldCheckFill, RiSparkling2Fill } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { Card, CardHeader, DemoBadge, IconTile, Pill } from "@/components/ui/surface";
import { DataTable, FilterPill, RowTitle, Toolbar, type Column } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { formatDate } from "@/lib/format";
import { useShop } from "@/lib/shop";
import { cx } from "@/utils/cx";

interface Tx {
  id: string;
  date: string;
  kind: "shop" | "event";
  title: string;
  sub: string;
  amount: number;
  status: "paid" | "refunded" | "upcoming";
  method: string;
}

/** Demo ledger. RecallDesk has no billing backend yet; nothing here is charged. */
const TX: Tx[] = [
  { id: "RD-1048", date: "2026-11-01", kind: "shop", title: "Shop plan", sub: "Nov 2026 · renews automatically", amount: 15, status: "upcoming", method: "Visa •• 4242" },
  { id: "RD-1047", date: "2026-10-01", kind: "shop", title: "Shop plan", sub: "Oct 2026", amount: 15, status: "paid", method: "Visa •• 4242" },
  { id: "RD-1046", date: "2026-09-19", kind: "event", title: "Event pass", sub: "Fall kids' consignment sale · 412 intake items", amount: 49, status: "paid", method: "Visa •• 4242" },
  { id: "RD-1045", date: "2026-09-01", kind: "shop", title: "Shop plan", sub: "Sep 2026", amount: 15, status: "paid", method: "Visa •• 4242" },
  { id: "RD-1044", date: "2026-08-22", kind: "event", title: "Event pass", sub: "Back-to-school swap · cancelled by organizer", amount: 49, status: "refunded", method: "Visa •• 4242" },
  { id: "RD-1043", date: "2026-08-01", kind: "shop", title: "Shop plan", sub: "Aug 2026", amount: 15, status: "paid", method: "Visa •• 4242" },
  { id: "RD-1042", date: "2026-07-18", kind: "shop", title: "Shop plan", sub: "First month · started with the Jul 18 recalls", amount: 15, status: "paid", method: "Visa •• 4242" },
];

const STATUS = { paid: { tone: "green", label: "Paid" }, refunded: { tone: "gray", label: "Refunded" }, upcoming: { tone: "amber", label: "Upcoming" } } as const;

function Wordmark({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cx("inline-flex h-7 items-center rounded-md border border-line bg-card px-2 text-caption-1-bold tracking-tight text-text-secondary", className)}>{children}</span>;
}

export function BillingView() {
  const shop = useShop();
  const [period, setPeriod] = useState<"all" | "shop" | "event">("all");
  const rows = TX.filter((t) => period === "all" || t.kind === period);
  const paid = TX.filter((t) => t.status === "paid").reduce((a, t) => a + t.amount, 0);

  const columns: Column<Tx>[] = [
    {
      id: "desc",
      header: "Description",
      mobile: "primary",
      width: "36%",
      sort: (t) => t.title,
      cell: (t) => <RowTitle leading={<IconTile icon={t.kind === "event" ? RiSparkling2Fill : RiFileTextLine} tone={t.kind === "event" ? "violet" : "blue"} size="sm" />} title={t.title} sub={t.sub} />,
    },
    { id: "date", header: "Date", mobile: "meta", width: "14%", sort: (t) => t.date, cell: (t) => <span className="text-body-2-medium whitespace-nowrap text-text-primary">{formatDate(t.date, { month: "short", day: "numeric", year: "numeric" })}</span> },
    { id: "amount", header: "Amount", mobile: "meta", width: "11%", align: "end", sort: (t) => t.amount, cell: (t) => <span className={cx("text-body-2-semibold tabular-nums", t.status === "refunded" ? "text-text-tertiary line-through" : "text-text-primary")}>${t.amount.toFixed(2)}</span> },
    { id: "status", header: "Status", mobile: "badge", width: "13%", sort: (t) => t.status, cell: (t) => <Pill size="sm" tone={STATUS[t.status].tone} dot>{STATUS[t.status].label}</Pill> },
    { id: "method", header: "Method", mobile: "meta", width: "14%", hideBelow: "lg", cell: (t) => <span className="text-body-2-regular whitespace-nowrap text-text-secondary">{t.method}</span> },
    { id: "inv", header: "Invoice", mobile: "hidden", width: "12%", hideBelow: "xl", cell: (t) => <span className="rd-mono text-caption-1-regular whitespace-nowrap text-text-tertiary">{t.id}</span> },
  ];

  const demo = () => toast({ title: "Demo billing", description: "There's no payment processor behind this page yet. Nothing was changed or charged.", status: "information" });

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Settings
            </Pill>
            <DemoBadge>Demo · no charges</DemoBadge>
          </>
        }
        title="Billing"
        description={`Plan and payments for ${shop.name}. Shop is $15 a month per shop; an Event pass is $49 per consignment event.`}
        actions={
          <>
            <Button variant="secondary" leadingIcon={RiDownload2Line} onClick={demo}>
              Download invoices
            </Button>
            <Button leadingIcon={RiExchangeDollarLine} onClick={demo}>
              Change plan
            </Button>
          </>
        }
      />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <CardHeader title="Transaction history" description={`$${paid.toFixed(2)} paid since July 18, 2026`} />
          <Toolbar className="border-t">
            <p className="text-caption-1-regular text-text-tertiary">Receipts go to {shop.email}</p>
            <FilterPill
              label="Type"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "all", label: "All", count: TX.length },
                { value: "shop", label: "Shop plan", count: TX.filter((t) => t.kind === "shop").length },
                { value: "event", label: "Event pass", count: TX.filter((t) => t.kind === "event").length },
              ]}
            />
          </Toolbar>
          <DataTable caption="Transaction history" rows={rows} columns={columns} rowKey={(t) => t.id} initialSort={{ id: "date", dir: "desc" }} pageSize={8} footerNote="Demo ledger · amounts in USD, taxes not shown" />
        </Card>

        <aside className="flex flex-col gap-5" aria-label="Plan">
          <Card className="flex flex-col items-center gap-3 px-6 py-7 text-center">
            <span className="relative flex items-center justify-center" aria-hidden>
              <span className="absolute size-20 rounded-full bg-clear-surface" />
              <span className="absolute size-14 rounded-full bg-clear-surface ring-1 ring-clear-border" />
              <RiShieldCheckFill className="relative size-8 text-clear-solid" />
            </span>
            <p className="mt-4 text-headline-semibold text-text-primary">Your payments are secure</p>
            <p className="text-body-2-regular text-text-tertiary">Card details would be held by the payment processor, never by RecallDesk. Cancel any time; the Thursday card keeps working until the period ends.</p>
            <div className="mt-1 flex flex-wrap justify-center gap-1.5" aria-label="Accepted payment methods">
              <Wordmark className="italic">VISA</Wordmark>
              <Wordmark>Mastercard</Wordmark>
              <Wordmark>AMEX</Wordmark>
              <Wordmark>Apple Pay</Wordmark>
            </div>
            <p className="flex items-center gap-1 text-caption-1-regular text-text-tertiary">
              <RiLockLine className="size-3.5" aria-hidden /> 256-bit TLS
            </p>
          </Card>

          <Card>
            <CardHeader title="Subscription preview" actions={<Pill size="sm" tone="green" dot>Active</Pill>} />
            <div className="flex flex-col gap-4 border-t border-line px-5 py-5">
              <div>
                <p className="text-caption-1-medium text-text-tertiary">Shop plan · {shop.short}</p>
                <p className="mt-1 flex items-baseline gap-1">
                  <span className="rd-highlight text-display-3-semibold tracking-[-0.03em] text-text-primary tabular-nums">$15</span>
                  <span className="text-body-medium text-text-tertiary">/ month</span>
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-line bg-subtle px-3 py-2.5">
                  <dt className="text-caption-1-medium text-text-tertiary">Previous payment</dt>
                  <dd className="text-body-2-semibold text-text-primary">Oct 1, 2026</dd>
                </div>
                <div className="rounded-lg border border-line bg-subtle px-3 py-2.5">
                  <dt className="text-caption-1-medium text-text-tertiary">Next payment</dt>
                  <dd className="text-body-2-semibold text-text-primary">Nov 1, 2026</dd>
                </div>
              </dl>
              <div className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
                <IconTile icon={RiBankCardLine} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-body-2-semibold whitespace-nowrap text-text-primary">Visa •• 4242</p>
                  <p className="text-caption-1-regular text-text-tertiary">Expires 08/28</p>
                </div>
                <Button size="small" variant="secondary" onClick={demo}>
                  Change method
                </Button>
              </div>
              <div className="flex items-center justify-between gap-2 border-t border-line pt-4">
                <button type="button" onClick={demo} className="cursor-pointer rounded text-body-2-semibold text-stop-text outline-none hover:underline focus-visible:ring-2 focus-visible:ring-border-focus-ring">
                  Cancel plan
                </button>
                <span className="text-caption-1-regular text-text-tertiary">Billed monthly</span>
              </div>
            </div>
          </Card>

          <Card className="rd-promo relative overflow-hidden border-0 p-5 text-white">
            <div className="rd-dots pointer-events-none absolute inset-0 opacity-50" aria-hidden />
            <div className="relative flex flex-col gap-2">
              <p className="text-caption-1-semibold text-white/80">Running a consignment sale?</p>
              <p className="text-title-3-semibold">Event pass · $49</p>
              <p className="text-caption-1-regular text-white/80">Every consignor&apos;s intake list, one card per drop-off batch, recalls back to 2023.</p>
              <button type="button" onClick={demo} className="mt-1 inline-flex h-8 w-fit cursor-pointer items-center gap-1.5 rounded-lg bg-white px-3 text-body-2-semibold text-accent-700 outline-none hover:bg-white/90 focus-visible:ring-2 focus-visible:ring-white/70">
                <RiSparkling2Fill className="size-4" aria-hidden /> Add an event
              </button>
            </div>
          </Card>
        </aside>
      </div>
    </Page>
  );
}

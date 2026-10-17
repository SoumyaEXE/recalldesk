"use client";

import { useMemo, useState } from "react";
import { RiBrainLine, RiCheckboxCircleLine, RiDatabase2Line, RiDeleteBin6Line, RiRefreshLine, RiSparklingLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { NavButton } from "@/components/rd/nav-button";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Card, CardHeader, DemoBadge, EmptyState, IconTile, Pill, VerdictPill } from "@/components/ui/surface";
import { DataTable, SearchField, Toolbar, type Column } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { getLatestCard, getMemories } from "@/lib/api";
import { formatDate, relativeTime } from "@/lib/format";
import { useShop } from "@/lib/shop";
import type { AppliedMemory, Memory } from "@/lib/types";
import { useLoad } from "@/lib/use-load";

type M = Memory & { item?: string | null; note?: string | null; backend?: string; applied: number };

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function appliedCount(m: Memory & { item?: string | null }, applied: (AppliedMemory & { item?: string; recall_number?: string })[]) {
  return applied.filter((a) => a.memory_id === m.memory_id || (m.recall_number && a.recall_number === m.recall_number && (!m.item || !a.item || norm(a.item) === norm(m.item)))).length;
}

export function MemoryView() {
  const shop = useShop();
  const mem = useLoad(() => getMemories(shop.id), `mem-${shop.id}`);
  const card = useLoad(() => getLatestCard(shop.id), `card-${shop.id}`);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");

  const applied = useMemo(() => (card.data?.card?.applied_memories ?? []) as (AppliedMemory & { item?: string; recall_number?: string })[], [card.data]);
  const rows = useMemo<M[]>(() => {
    const t = q.trim().toLowerCase();
    return (mem.data ?? [])
      .filter((m) => !hidden.has(m.memory_id))
      .map((m) => ({ ...(m as M), applied: appliedCount(m as M, applied) }))
      .filter((m) => !t || `${m.text} ${m.recall_number ?? ""}`.toLowerCase().includes(t));
  }, [mem.data, hidden, applied, q]);
  const backend = rows.find((m) => m.backend)?.backend ?? (mem.source === "live" ? "backboard" : "fixture");

  const columns: Column<M>[] = [
    {
      id: "memory",
      header: "Memory",
      mobile: "primary",
      width: "44%",
      cell: (m) => (
        <span className="flex min-w-0 items-start gap-3 py-2">
          <IconTile icon={RiBrainLine} tone="blue" size="sm" />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate text-body-2-semibold text-text-primary">{m.item ?? m.text.match(/'([^']+)'/)?.[1] ?? "Shop rule"}</span>
            <span className="line-clamp-2 text-caption-1-regular whitespace-normal text-text-tertiary">{m.note ?? m.text.replace(/^Shop correction: /, "").replace(/\s*\[recall=.*\]$/, "")}</span>
          </span>
        </span>
      ),
    },
    { id: "recall", header: "Recall #", mobile: "meta", width: "11%", sort: (m) => m.recall_number ?? "", cell: (m) => (m.recall_number ? <span className="rd-mono text-body-2-medium text-text-primary">#{m.recall_number}</span> : "—") },
    { id: "override", header: "Override", mobile: "badge", width: "15%", cell: (m) => (m.correct_verdict ? <VerdictPill verdict={m.correct_verdict} label={m.correct_verdict === "no_match" ? "Not recalled" : undefined} /> : <Pill size="sm">Note</Pill>) },
    { id: "created", header: "Created", mobile: "meta", width: "12%", sort: (m) => m.created_at ?? "", cell: (m) => <span className="text-body-2-medium whitespace-nowrap text-text-primary">{m.created_at ? formatDate(m.created_at, { month: "short", day: "numeric" }) : "—"}</span> },
    { id: "applied", header: "Applied", mobile: "meta", width: "11%", sort: (m) => m.applied, cell: (m) => <span className="text-body-2-medium text-text-primary tabular-nums">{m.applied}×<span className="text-caption-1-regular text-text-tertiary"> this week</span></span> },
    {
      id: "actions",
      header: <span className="sr-only">Actions</span>,
      mobile: "meta",
      mobileLabel: "Actions",
      width: "7%",
      align: "end",
      cell: (m) => (
        <Button
          size="small"
          variant="secondary"
          iconOnly
          leadingIcon={RiDeleteBin6Line}
          aria-label={`Remove memory ${m.memory_id}`}
          onClick={() => {
            setHidden((h) => new Set(h).add(m.memory_id));
            toast({ title: "Removed from this view", description: `Memory ${m.memory_id.slice(0, 12)}… is hidden here. The API doesn't expose a delete yet, so it stays in Backboard.`, status: "information" });
          }}
        />
      ),
    },
  ];

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Backboard · one assistant per shop
            </Pill>
            <DemoBadge show={mem.placeholder || mem.source === "fixture"}>{mem.source === "fixture" ? "Recorded fixture" : "Demo"}</DemoBadge>
          </>
        }
        title="Shop memory"
        description={`Corrections ${shop.short} made ("ours is the 2022 one, not recalled"). Stored as Backboard memories, retrieved semantically every Thursday and applied by code, so the same false alarm never comes back.`}
        actions={
          <>
            <Button variant="secondary" leadingIcon={RiRefreshLine} onClick={mem.reload}>
              Refresh
            </Button>
            <NavButton href="/inventory" leadingIcon={RiSparklingLine}>
              Correct an item
            </NavButton>
          </>
        }
      />

      <KpiRow className="mb-6">
        <KpiCard index={0} icon={RiBrainLine} tone="blue" label="Memories" value={rows.length} loading={mem.loading} status="Saved" caption="Corrections and shop rules" />
        <KpiCard index={1} icon={RiCheckboxCircleLine} tone="green" label="Applied this week" value={applied.length} loading={card.loading} status="On the card" caption="Overrode the model's verdict" />
        <KpiCard index={2} icon={RiSparklingLine} tone="amber" label="False alarms cleared" value={rows.filter((m) => m.correct_verdict === "no_match").length} loading={mem.loading} status="Not recalled" caption="Marked clear by the shop" />
        <KpiCard index={3} icon={RiDatabase2Line} tone="gray" label="Memory backend" display={<span className="capitalize">{backend.startsWith("local") ? "Local" : backend}</span>} loading={mem.loading} status={mem.source === "live" ? "Connected" : "Fixture"} caption={backend.startsWith("local") ? "No BACKBOARD_API_KEY" : "Semantic retrieval per shop"} />
      </KpiRow>

      <Card>
        <CardHeader title="Memories" description="Newest first. Each one came from a “Not a match? Correct this” on a card or drawer." />
        <Toolbar className="border-t">
          <SearchField value={q} onChange={setQ} placeholder="Search memories, recall #…" label="Search memories" className="md:max-w-[320px] md:flex-1" />
        </Toolbar>
        <DataTable
          caption="Shop memories"
          rows={rows}
          columns={columns}
          rowKey={(m) => m.memory_id}
          loading={mem.loading}
          initialSort={{ id: "created", dir: "desc" }}
          empty={
            <EmptyState icon={RiBrainLine} tone="blue" title="No memories yet" action={<NavButton href="/inventory" size="small" variant="secondary">Open inventory</NavButton>}>
              When a card flags something that isn&apos;t the recalled product, correct it once. It&apos;s remembered for this shop.
            </EmptyState>
          }
        />
      </Card>
      {applied.length > 0 && (
        <Card className="mt-5">
          <CardHeader title="Applied on this week's card" description={card.data?.card ? `card ${card.data.card.id}` : undefined} />
          <ul className="flex flex-col border-t border-line">
            {applied.map((a) => (
              <li key={a.memory_id} className="flex flex-col gap-1 border-b border-line px-5 py-3 last:border-b-0 sm:flex-row sm:items-center sm:gap-4">
                <code className="rd-mono shrink-0 text-caption-1-medium text-text-tertiary">{a.memory_id}</code>
                <span className="min-w-0 flex-1 text-body-2-regular text-text-secondary">{a.text.replace(/^Shop correction: /, "").replace(/\s*\[recall=.*\]$/, "")}</span>
                {card.data?.card?.generated_at && <span className="shrink-0 text-caption-1-regular text-text-tertiary">{relativeTime(card.data.card.generated_at)}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Page>
  );
}

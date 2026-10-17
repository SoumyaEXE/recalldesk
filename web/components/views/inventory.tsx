"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  RiArchiveStackLine,
  RiArrowGoBackLine,
  RiCheckboxCircleLine,
  RiClipboardLine,
  RiErrorWarningLine,
  RiExternalLinkLine,
  RiFileUploadLine,
  RiFilter3Line,
  RiInboxLine,
  RiPlayCircleFill,
  RiPrinterLine,
  RiSparklingLine,
} from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { FileUpload } from "@/components/base/file-upload/file-upload";
import { Textarea } from "@/components/base/textarea/textarea";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { ItemDrawer, type FlaggedItem } from "@/components/rd/item-drawer";
import { NavButton } from "@/components/rd/nav-button";
import { StepTimeline } from "@/components/rd/step-timeline";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Dialog } from "@/components/ui/overlay";
import { Card, CardHeader, DemoBadge, EmptyState, Pill, VerdictPill } from "@/components/ui/surface";
import { DataTable, FilterPill, RowAvatar, RowTitle, SearchField, Toolbar, type Column } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { getCardStatus, getInventory, getLatestCard, getRecalls, isSimulated, startCheck, type InventoryRow } from "@/lib/api";
import { joinInventory, type InventoryVerdict } from "@/lib/inventory";
import { parseItems } from "@/lib/match";
import { useShop } from "@/lib/shop";
import type { CardStatus, InventoryItem, Verdict } from "@/lib/types";
import { useLoad } from "@/lib/use-load";

const TEMPORAL_UI = "http://localhost:8233";
const POLL_MS = 900;

const SAMPLE = `name,brand,model,notes
Bedside sleeper bassinet gray stars & moon,Papablic,PAPA03001AI,consignor #212
Elmo silicone teether with crayon box,Skip Hop,9R263210,
Lights and Sound Fire Truck,Melissa & Doug,,box missing
Rainbow rattle wooden teething toy,HABA,,
Portable sleep machine with nightlight,Love to Dream,,
Nordi toddler tower white,HARPPA,,
Thermal laminator 13 inch,Scotch,TL1302Z,office shelf
Wooden fire truck puzzle,Melissa & Doug,,
Pack 'n Play playard,Graco,,2023 tag
Footie pajamas 12M,Carter's,,
Baby bath seat with suction cups,,,no brand on tag
Board book bundle (5),,,`;

type Row = InventoryVerdict;

export function InventoryView() {
  const shop = useShop();
  const inventory = useLoad(() => getInventory(shop.id), `inv-${shop.id}`);
  const latest = useLoad(() => getLatestCard(shop.id), `card-${shop.id}`);
  const recalls = useLoad(getRecalls, "recalls");
  const byNumber = useMemo(() => new Map((recalls.data ?? []).map((r) => [r.recall_number, r])), [recalls.data]);

  const params = useSearchParams();
  const [pasteOpen, setPasteOpen] = useState(() => params.get("new") === "1");
  const [importOpen, setImportOpen] = useState(false);
  const [text, setText] = useState("");
  const [runItems, setRunItems] = useState<InventoryRow[] | null>(null);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [status, setStatus] = useState<CardStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [q, setQ] = useState("");
  const [vf, setVf] = useState<"all" | Verdict>("all");
  const [cat, setCat] = useState("all");
  const [open, setOpen] = useState<FlaggedItem | null>(null);
  const parsed = useMemo(() => parseItems(text), [text]);

  useEffect(() => {
    if (!workflowId) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const r = await getCardStatus(workflowId);
        if (!alive) return;
        setStatus(r.data);
        if (r.data.status !== "completed" && r.data.status !== "failed") timer = window.setTimeout(tick, POLL_MS);
        else if (r.data.card) toast({ title: "Check finished", description: `${r.data.card.do_not_sell.length} do not sell · ${r.data.card.check_label.length} check label · card ready to print.`, status: "success" });
      } catch (e) {
        if (alive) toast({ title: "Couldn't read the workflow", description: String(e), status: "error" });
      }
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [workflowId]);

  const run = async (items: InventoryItem[], rows: InventoryRow[] | null) => {
    if (!items.length) return;
    setStarting(true);
    setStatus(null);
    const r = await startCheck(items, shop.id);
    setStarting(false);
    setRunItems(rows);
    setWorkflowId(r.workflow_id);
  };

  const runAll = () => {
    const rows = inventory.data ?? [];
    run(
      rows.map((r) => ({ name: r.name, brand: r.brand, model: r.model, notes: r.notes })),
      null,
    );
  };

  const runPasted = () => {
    const rows: InventoryRow[] = parsed.map((it, i) => ({ sku: `NEW-${String(i + 1).padStart(2, "0")}`, name: it.name, brand: it.brand, model: it.model, notes: it.notes, category: "new intake" }));
    setPasteOpen(false);
    setImportOpen(false);
    run(parsed, rows);
  };

  const done = status?.status === "completed";
  const running = !!workflowId && !done && status?.status !== "failed";
  const activeCard = done && status?.card ? status.card : latest.data?.card;
  const rows = useMemo(() => joinInventory(runItems ?? inventory.data ?? [], running && runItems ? undefined : activeCard).rows, [inventory.data, activeCard, running, runItems]);

  const counts = useMemo(() => ({ match: rows.filter((r) => r.verdict === "match").length, check: rows.filter((r) => r.verdict === "check").length, no_match: rows.filter((r) => r.verdict === "no_match").length }), [rows]);
  const categories = useMemo(() => [...new Set(rows.map((r) => r.inv.category).filter(Boolean) as string[])].sort(), [rows]);
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return rows
      .filter((r) => vf === "all" || r.verdict === vf)
      .filter((r) => cat === "all" || r.inv.category === cat)
      .filter((r) => !t || `${r.inv.name} ${r.inv.brand ?? ""} ${r.inv.model ?? ""} ${r.inv.sku} ${r.flag?.recall_number ?? ""}`.toLowerCase().includes(t));
  }, [rows, vf, cat, q]);

  const order: Record<Verdict, number> = { match: 0, check: 1, no_match: 2 };
  const columns: Column<Row>[] = [
    {
      id: "item",
      header: "Item",
      mobile: "primary",
      width: "34%",
      sort: (r) => r.inv.name,
      cell: (r) => (
        <RowTitle
          leading={<RowAvatar label={r.inv.brand ?? r.inv.name} tone={r.verdict === "match" ? "red" : r.verdict === "check" ? "amber" : "gray"} />}
          title={r.inv.name}
          sub={
            <>
              <span className="rd-mono">{r.inv.sku}</span>
              {r.inv.brand && ` · ${r.inv.brand}`}
            </>
          }
        />
      ),
    },
    { id: "model", header: "Model", mobile: "meta", width: "14%", sort: (r) => r.inv.model ?? "", cell: (r) => (r.inv.model ? <span className="rd-mono text-body-2-medium text-text-primary">{r.inv.model}</span> : <span className="text-text-tertiary">—</span>) },
    { id: "cat", header: "Category", mobile: "meta", width: "13%", hideBelow: "lg", sort: (r) => r.inv.category ?? "", cell: (r) => (r.inv.category ? <Pill size="sm">{r.inv.category}</Pill> : null) },
    { id: "price", header: "Price", mobile: "meta", width: "9%", align: "end", hideBelow: "xl", sort: (r) => Number((r.inv.price ?? "").replace(/[^0-9.]/g, "")) || 0, cell: (r) => <span className="text-body-2-medium text-text-primary tabular-nums">{r.inv.price ?? "—"}</span> },
    { id: "verdict", header: "Verdict", mobile: "badge", width: "15%", sort: (r) => order[r.verdict], cell: (r) => (running && runItems ? <Pill size="sm">Checking…</Pill> : <VerdictPill verdict={r.verdict} />) },
    { id: "recall", header: "Recall #", mobile: "meta", width: "11%", sort: (r) => r.flag?.recall_number ?? "", cell: (r) => (r.flag ? <span className="rd-mono text-body-2-medium text-text-primary">#{r.flag.recall_number}</span> : <span className="text-text-tertiary">—</span>) },
  ];

  // With the live-check panel open the table is narrower: drop the least useful columns.
  const shown = workflowId ? columns.filter((c) => c.id !== "price" && c.id !== "cat") : columns;
  const k = rows.length;
  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" dot tone="blue">
              {shop.short}
            </Pill>
            {runItems && <Pill size="sm" tone="amber">Showing {runItems.length} new intake items</Pill>}
          </>
        }
        title="Inventory"
        description="Every item in the shop, checked against every CPSC recall since July 18. Paste or import new intake to check it before it hits the floor."
        actions={
          <>
            <Button variant="secondary" leadingIcon={RiFileUploadLine} onClick={() => setImportOpen(true)}>
              Import CSV
            </Button>
            <Button variant="secondary" leadingIcon={RiClipboardLine} onClick={() => setPasteOpen(true)}>
              Paste items
            </Button>
            <Button leadingIcon={RiPlayCircleFill} onClick={runAll} disabled={starting || running || !inventory.data?.length}>
              {running ? "Checking…" : `Check all ${inventory.data?.length ?? ""} items`}
            </Button>
          </>
        }
      />

      <KpiRow className="mb-6">
        <KpiCard index={0} icon={RiArchiveStackLine} tone="blue" label={runItems ? "Items in this check" : "Items in inventory"} value={k} loading={inventory.loading} status={runItems ? "New intake" : "Watched"} caption={`${categories.length} categories`} />
        <KpiCard index={1} icon={RiErrorWarningLine} tone="red" label="Do not sell" value={counts.match} loading={inventory.loading || latest.loading} status="Pull now" caption="Recalled identifier on the item" />
        <KpiCard index={2} icon={RiInboxLine} tone="amber" label="Check label" value={counts.check} loading={inventory.loading || latest.loading} status="Look first" caption="Label decides it" />
        <KpiCard index={3} icon={RiCheckboxCircleLine} tone="green" label="Clear" value={counts.no_match} loading={inventory.loading || latest.loading} status="OK to list" caption="No recall matched" />
      </KpiRow>

      <div className={workflowId ? "grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]" : ""}>
        <Card className="min-w-0">
          <Toolbar>
            <SearchField value={q} onChange={setQ} placeholder="Search name, brand, model, SKU…" label="Search inventory" className="md:max-w-[320px] md:flex-1" />
            <div className="flex flex-wrap items-center gap-2">
              <RiFilter3Line className="hidden size-4 text-foreground-icon-tertiary md:block" aria-hidden />
              <FilterPill
                label="Status"
                value={vf}
                onChange={setVf}
                options={[
                  { value: "all", label: "All", count: rows.length },
                  { value: "match", label: "Do not sell", count: counts.match },
                  { value: "check", label: "Check label", count: counts.check },
                  { value: "no_match", label: "Clear", count: counts.no_match },
                ]}
              />
              <FilterPill label="Category" value={cat} onChange={setCat} options={[{ value: "all", label: "All" }, ...categories.map((c) => ({ value: c, label: c, count: rows.filter((r) => r.inv.category === c).length }))]} />
              {runItems && (
                <Button
                  size="small"
                  variant="ghost"
                  leadingIcon={RiArrowGoBackLine}
                  onClick={() => {
                    setRunItems(null);
                    setWorkflowId(null);
                    setStatus(null);
                  }}
                >
                  Back to inventory
                </Button>
              )}
            </div>
          </Toolbar>
          <DataTable
            caption="Shop inventory"
            rows={filtered}
            columns={shown}
            rowKey={(r) => r.inv.sku}
            rowLabel={(r) => `Open ${r.inv.name}`}
            onRowOpen={(r) => setOpen(r.flag ?? { label: r.inv.name, verdict: "no_match", recall_number: "", inv: r.inv })}
            loading={inventory.loading}
            initialSort={{ id: "verdict", dir: "asc" }}
            pageSize={10}
            empty={
              <EmptyState icon={RiInboxLine} title={rows.length ? "Nothing matches these filters" : "No items yet"} action={<Button size="small" variant="secondary" onClick={() => setPasteOpen(true)}>Paste items</Button>}>
                {rows.length ? "Try clearing the search or the status filter." : "Paste a list or import a CSV with name, brand, model, notes."}
              </EmptyState>
            }
          />
        </Card>

        {workflowId && (
          <Card as="aside" aria-label="Live check" className="rd-rise xl:sticky xl:top-6">
            <CardHeader
              title={running ? "Checking…" : done ? "Check complete" : "Workflow"}
              description={<span className="rd-mono text-caption-1-regular break-all">{workflowId}</span>}
              actions={isSimulated(workflowId) ? <DemoBadge>Simulated · API offline</DemoBadge> : <Pill size="sm" tone="blue" dot>Temporal</Pill>}
            />
            <div className="border-t border-line px-5 py-4">{status ? <StepTimeline steps={status.steps} dense /> : <p className="text-body-2-regular text-text-tertiary">Starting InventoryCheckWorkflow…</p>}</div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line bg-subtle px-5 py-3">
              {done && (
                <NavButton href="/cards" size="small" leadingIcon={RiPrinterLine}>
                  Open card
                </NavButton>
              )}
              {!isSimulated(workflowId) && (
                <a href={`${TEMPORAL_UI}/namespaces/default/workflows/${encodeURIComponent(workflowId)}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
                  Open in Temporal UI <RiExternalLinkLine className="size-3.5" aria-hidden />
                </a>
              )}
              <span className="ms-auto text-caption-1-regular text-text-tertiary">Retried on bad JSON · resumed if a worker dies</span>
            </div>
          </Card>
        )}
      </div>

      <Dialog
        isOpen={pasteOpen}
        onOpenChange={setPasteOpen}
        size="lg"
        title="Paste items"
        description="One item per line, or CSV with a header row (name, brand, model, notes). We check them against every recall and give you a card."
        footer={
          <>
            <Button variant="ghost" size="small" leadingIcon={RiSparklingLine} onClick={() => setText(SAMPLE)} className="me-auto">
              Use sample
            </Button>
            <Button variant="secondary" size="small" onClick={() => setPasteOpen(false)}>
              Cancel
            </Button>
            <Button size="small" leadingIcon={RiPlayCircleFill} onClick={runPasted} disabled={!parsed.length || starting}>
              {parsed.length ? `Check ${parsed.length} item${parsed.length === 1 ? "" : "s"}` : "Check items"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Textarea
            label="Items"
            value={text}
            onChange={setText}
            rows={10}
            resize="vertical"
            placeholder={"Graco Pack 'n Play, gray\nSkip Hop Elmo teether 9R263210\nMelissa & Doug fire truck\n…"}
            fieldClassName="font-mono"
          />
          {parsed.length > 0 && (
            <ul className="rd-scroll flex max-h-40 flex-col gap-1 overflow-y-auto rounded-xl border border-line bg-subtle p-2" aria-label="Parsed items">
              {parsed.slice(0, 50).map((it, i) => (
                <li key={i} className="flex min-w-0 items-baseline gap-2 text-caption-1-regular">
                  <span className="w-5 shrink-0 text-end text-text-tertiary tabular-nums">{i + 1}</span>
                  <span className="truncate text-text-primary">{it.name}</span>
                  {it.brand && <span className="shrink-0 text-text-secondary">{it.brand}</span>}
                  {it.model && <code className="rd-mono shrink-0 text-text-tertiary">{it.model}</code>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Dialog>

      <Dialog
        isOpen={importOpen}
        onOpenChange={setImportOpen}
        title="Import CSV"
        description="Columns: name, brand, model, notes (header row optional). Up to 2 MB."
        footer={
          <>
            <Button variant="secondary" size="small" onClick={() => setImportOpen(false)}>
              Cancel
            </Button>
            <Button size="small" leadingIcon={RiPlayCircleFill} onClick={runPasted} disabled={!parsed.length || starting}>
              {parsed.length ? `Check ${parsed.length} item${parsed.length === 1 ? "" : "s"}` : "Check items"}
            </Button>
          </>
        }
      >
        <FileUpload
          allowedExtensions={["csv", "txt"]}
          maxBytes={2 * 1024 * 1024}
          onUploadComplete={async (f) => {
            const t = await f.text();
            const first = t.split(/\r?\n/)[0]?.toLowerCase() ?? "";
            setText(f.name.endsWith(".csv") && !first.includes("name") ? `name,brand,model,notes\n${t}` : t);
          }}
        />
        {parsed.length > 0 && <p className="mt-3 text-body-2-medium text-text-primary">{parsed.length} items ready to check.</p>}
      </Dialog>

      <ItemDrawer item={open} recall={open?.recall_number ? byNumber.get(open.recall_number) : undefined} shopId={shop.id} onClose={() => setOpen(null)} totalRecalls={recalls.data?.length} />
    </Page>
  );
}

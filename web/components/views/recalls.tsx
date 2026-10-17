"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { RiEyeOffLine, RiExternalLinkLine, RiMapPin2Line, RiParentLine, RiShieldFlashLine, RiShoppingBag3Line, RiToolsLine, RiFileSearchLine } from "@remixicon/react";
import { ButtonLink } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { HighlightIds } from "@/components/rd/ids";
import { recallIds } from "@/components/rd/item-drawer";
import { NavButton } from "@/components/rd/nav-button";
import { RecallImage } from "@/components/rd/recall-image";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Drawer } from "@/components/ui/overlay";
import { Card, ChildrensPill, DemoBadge, EmptyState, Eyebrow, IconTile, IdChip, KeyValue, Pill } from "@/components/ui/surface";
import { DataTable, FilterPill, RowAvatar, RowTitle, SearchField, Toolbar, type Column } from "@/components/ui/table";
import { getRecalls, getScan } from "@/lib/api";
import { formatDate, num, shortTitle, soldWindow } from "@/lib/format";
import type { RecallRecord, ScanByRecall } from "@/lib/types";
import { useLoad } from "@/lib/use-load";

/** Verified count for corpus A (docs/charts/README.md "buried" definition); used only if the field is absent. */
const BURIED_VERIFIED = 73;

type R = RecallRecord & { ids_only_in_description?: boolean; scan?: ScanByRecall };

function RecallDrawer({ r: current, onClose }: { r: R | null; onClose: () => void }) {
  const [kept, setKept] = useState(current);
  if (current && current !== kept) setKept(current);
  const r = current ?? kept;
  const s = r?.spec;
  const ids = recallIds(r ?? undefined);
  return (
    <Drawer
      isOpen={!!current}
      onOpenChange={(o) => !o && onClose()}
      width="lg"
      title={r ? shortTitle(r.title) : ""}
      leading={r ? <RecallImage src={r.images[0]} label={s?.product_type ?? "recalled product"} size={48} /> : undefined}
      subtitle={
        r && (
          <span className="flex flex-wrap items-center gap-2">
            <span className="rd-mono text-text-secondary">CPSC #{r.recall_number}</span>
            <span>· {formatDate(r.recall_date)}</span>
            {r.is_childrens && <ChildrensPill size="sm" />}
            {r.ids_only_in_description && (
              <Pill size="sm" tone="amber" icon={RiEyeOffLine}>
                ID only in fine print
              </Pill>
            )}
          </span>
        )
      }
      footer={
        r && (
          <>
            <NavButton href={`/ebay?open=${r.recall_number}`} variant="secondary" size="small" leadingIcon={RiShoppingBag3Line}>
              eBay listings
            </NavButton>
            <ButtonLink href={r.url} target="_blank" rel="noreferrer" size="small" trailingIcon={RiExternalLinkLine}>
              Read on cpsc.gov
            </ButtonLink>
          </>
        )
      }
    >
      {r && (
        <div className="flex flex-col gap-6">
          {r.images.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {r.images.slice(0, 5).map((src, i) => (
                <RecallImage key={src} src={src} label={`${s?.product_type ?? "product"} photo ${i + 1}`} size={96} />
              ))}
            </div>
          )}

          {s?.look_for && (
            <div className="flex gap-3 rounded-xl border border-info-border bg-info-surface p-4">
              <IconTile icon={RiMapPin2Line} tone="blue" size="sm" className="bg-card" />
              <div className="min-w-0">
                <p className="text-body-2-semibold text-text-primary">Where to look</p>
                <p className="text-body-2-regular text-text-secondary">
                  <HighlightIds text={s.look_for} />
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="flex min-w-0 flex-col gap-3">
              <Eyebrow>Original CPSC text</Eyebrow>
              <p className="text-body-2-regular leading-6 text-text-primary">
                <HighlightIds text={r.description} ids={ids} />
              </p>
              {r.retailers[0] && <p className="text-caption-1-regular text-text-tertiary">{r.retailers.join(" ")}</p>}
            </section>
            <section className="flex min-w-0 flex-col gap-2 rounded-xl border border-line bg-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Eyebrow>Extracted spec</Eyebrow>
                {s?.spec_source && <Pill size="sm" tone={s.spec_source === "teacher" ? "blue" : "gray"}>{s.spec_source === "teacher" ? "Teacher · Qwen3.5-397B" : s.spec_source}</Pill>}
              </div>
              {s ? (
                <dl className="divide-y divide-line">
                  <KeyValue k="Brand">{s.brand}</KeyValue>
                  <KeyValue k="Product">
                    {s.product_name} <span className="text-text-tertiary">· {s.product_type}</span>
                  </KeyValue>
                  <KeyValue k="Model nos.">
                    {s.model_numbers.length ? (
                      <span className="flex flex-wrap gap-1">
                        {s.model_numbers.map((m) => (
                          <IdChip key={m}>{m}</IdChip>
                        ))}
                      </span>
                    ) : (
                      <span className="text-text-tertiary">None stated</span>
                    )}
                  </KeyValue>
                  {(s.other_identifiers.length > 0 || s.upcs.length > 0) && (
                    <KeyValue k="Other IDs">
                      <span className="flex flex-wrap gap-1">
                        {[...s.other_identifiers, ...s.upcs].map((m) => (
                          <IdChip key={m} tone="gray">
                            {m}
                          </IdChip>
                        ))}
                      </span>
                    </KeyValue>
                  )}
                  <KeyValue k="Sold">{soldWindow(s.sold_from, s.sold_to)}</KeyValue>
                  {s.colors.length > 0 && <KeyValue k="Colors">{s.colors.join(", ")}</KeyValue>}
                  {s.key_features.length > 0 && (
                    <KeyValue k="Features">
                      <ul className="list-disc ps-4">
                        {s.key_features.map((f) => (
                          <li key={f}>{f}</li>
                        ))}
                      </ul>
                    </KeyValue>
                  )}
                  {r.units && <KeyValue k="Units">{r.units}</KeyValue>}
                  <KeyValue k="eBay queries">
                    <span className="flex flex-col gap-0.5">
                      {s.search_queries.map((q) => (
                        <code key={q} className="rd-mono text-caption-1-regular text-text-secondary">
                          {q}
                        </code>
                      ))}
                    </span>
                  </KeyValue>
                </dl>
              ) : (
                <p className="text-body-2-regular text-text-tertiary">Spec not extracted yet.</p>
              )}
            </section>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex gap-3 rounded-xl border border-line p-4">
              <IconTile icon={RiShieldFlashLine} tone="red" size="sm" />
              <div className="min-w-0">
                <p className="text-body-2-semibold text-text-primary">Hazard</p>
                <p className="text-body-2-regular text-text-secondary">{s?.hazard_short ?? r.hazards[0]}</p>
              </div>
            </div>
            <div className="flex gap-3 rounded-xl border border-line p-4">
              <IconTile icon={RiToolsLine} tone="green" size="sm" />
              <div className="min-w-0">
                <p className="text-body-2-semibold text-text-primary">Remedy</p>
                <p className="text-body-2-regular text-text-secondary">{s?.remedy_short ?? r.remedies[0]}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

export function RecallsView() {
  const recalls = useLoad(getRecalls, "recalls");
  const scan = useLoad(getScan, "scan");
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const openId = params.get("open");
  const [q, setQ] = useState("");
  const [period, setPeriod] = useState<"all" | "week" | "30" | "90">("all");
  const [cat, setCat] = useState<"all" | "kids" | "other">("all");
  const [fine, setFine] = useState<"all" | "fine">("all");

  const scanBy = useMemo(() => new Map((scan.data?.by_recall ?? []).map((x) => [x.recall_number, x])), [scan.data]);
  const all = useMemo<R[]>(() => (recalls.data ?? []).map((r) => ({ ...r, scan: scanBy.get(r.recall_number) })), [recalls.data, scanBy]);
  const latest = all.reduce((m, r) => (r.recall_date > m ? r.recall_date : m), "");
  const hasField = all.some((r) => typeof (r as R).ids_only_in_description === "boolean");
  const buried = hasField ? all.filter((r) => r.ids_only_in_description).length : BURIED_VERIFIED;
  const kids = all.filter((r) => r.is_childrens).length;

  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    const cutoff = (days: number) => {
      const d = new Date(`${latest}T12:00:00`);
      d.setDate(d.getDate() - days);
      return d.toISOString().slice(0, 10);
    };
    return all
      .filter((r) => (period === "all" ? true : period === "week" ? r.recall_date === latest : r.recall_date >= cutoff(Number(period))))
      .filter((r) => (cat === "all" ? true : cat === "kids" ? r.is_childrens : !r.is_childrens))
      .filter((r) => (fine === "all" ? true : !!r.ids_only_in_description))
      .filter((r) => !t || `${r.title} ${r.recall_number} ${r.spec?.brand ?? ""} ${recallIds(r).join(" ")}`.toLowerCase().includes(t));
  }, [all, q, period, cat, fine, latest]);

  const selected = openId ? (all.find((r) => r.recall_number === openId) ?? null) : null;
  const setOpen = (n: string | null) => {
    const sp = new URLSearchParams(params.toString());
    if (n) sp.set("open", n);
    else sp.delete("open");
    router.replace(`${pathname}${sp.size ? `?${sp}` : ""}`, { scroll: false });
  };

  const columns: Column<R>[] = [
    {
      id: "product",
      header: "Product",
      mobile: "primary",
      width: "34%",
      sort: (r) => shortTitle(r.title),
      cell: (r) => (
        <RowTitle
          leading={<RowAvatar label={r.spec?.brand ?? r.title} src={r.images[0]} icon={RiFileSearchLine} />}
          title={shortTitle(r.title)}
          sub={
            <>
              <span className="rd-mono">#{r.recall_number}</span> · {r.spec?.brand ?? r.manufacturers[0]}
            </>
          }
        />
      ),
    },
    { id: "date", header: "Date", mobile: "meta", width: "10%", sort: (r) => r.recall_date, cell: (r) => <span className="text-body-2-medium whitespace-nowrap text-text-primary tabular-nums">{formatDate(r.recall_date, { month: "short", day: "numeric" })}</span> },
    { id: "hazard", header: "Hazard", mobile: "meta", width: "20%", cell: (r) => <span className="line-clamp-2 text-caption-1-regular">{r.spec?.hazard_short ?? r.hazards[0]}</span> },
    { id: "units", header: "Units", mobile: "hidden", width: "10%", hideBelow: "xl", cell: (r) => <span className="line-clamp-2 text-caption-1-regular">{r.units?.replace(/^About /, "~") ?? "—"}</span> },
    {
      id: "cat",
      header: "Category",
      mobile: "badge",
      width: "13%",
      sort: (r) => (r.is_childrens ? 0 : 1),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          {r.is_childrens ? <ChildrensPill size="sm" /> : <Pill size="sm">General</Pill>}
          {r.ids_only_in_description && (
            <Pill size="sm" tone="amber" icon={RiEyeOffLine} className="xl:hidden">
              Fine print
            </Pill>
          )}
        </span>
      ),
    },
    { id: "ebay", header: "eBay", mobile: "meta", width: "7%", align: "end", hideBelow: "lg", sort: (r) => r.scan?.listings ?? 0, cell: (r) => <span className="text-body-2-medium text-text-primary tabular-nums">{r.scan ? num(r.scan.listings) : "—"}</span> },
    {
      id: "flagged",
      header: "Flagged",
      mobile: "meta",
      width: "8%",
      align: "end",
      sort: (r) => (r.scan ? r.scan.match * 1000 + r.scan.check : 0),
      cell: (r) =>
        r.scan ? (
          <span className="text-body-2-semibold tabular-nums">
            <span className={r.scan.match ? "text-stop-text" : "text-text-tertiary"}>{r.scan.match}</span>
            <span className="text-text-tertiary"> / </span>
            <span className={r.scan.check ? "text-caution-text" : "text-text-tertiary"}>{r.scan.check}</span>
          </span>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <Page>
      <PageHeader
        eyebrow={
          <Pill size="sm" tone="blue" dot>
            CPSC · since July 18, 2026
          </Pill>
        }
        title="Recalls"
        description="Every CPSC recall since July 18. Open one to see the original text with its identifiers highlighted, next to the identification spec the teacher model extracted from it."
        actions={
          <ButtonLink href="https://www.cpsc.gov/Recalls" target="_blank" rel="noreferrer" variant="secondary" trailingIcon={RiExternalLinkLine}>
            cpsc.gov/Recalls
          </ButtonLink>
        }
      />

      <KpiRow className="mb-6">
        <KpiCard index={0} icon={RiShieldFlashLine} tone="blue" label="Recalls since Jul 18" value={all.length || null} loading={recalls.loading} status={latest ? `Latest ${formatDate(latest, { month: "short", day: "numeric" })}` : undefined} caption="About a dozen every Thursday" />
        <KpiCard index={1} icon={RiParentLine} tone="green" label="Children's products" value={kids || null} loading={recalls.loading} status="Kids" caption={all.length ? `${Math.round((kids / all.length) * 100)}% of all recalls` : undefined} />
        <KpiCard
          index={2}
          icon={RiEyeOffLine}
          tone="amber"
          label="Model no. only in the fine print"
          value={buried}
          loading={recalls.loading}
          status="Buried"
          caption={hasField ? "ID appears only in the description" : "Verified count · see docs/charts"}
        />
        <KpiCard index={3} icon={RiShoppingBag3Line} tone="gray" label="eBay listings seen" value={scan.data?.listings_seen ?? null} loading={scan.loading} status={scan.placeholder ? undefined : "Scanned"} badge={<DemoBadge show={scan.placeholder} />} caption="SerpApi eBay engine" />
      </KpiRow>

      <Card>
        <Toolbar>
          <SearchField value={q} onChange={setQ} placeholder="Brand, product, model no., recall #" label="Search recalls" className="md:max-w-[320px] md:flex-1" />
          <div className="flex flex-wrap items-center gap-2">
            <FilterPill
              label="Period"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "all", label: "All time" },
                { value: "week", label: "This week" },
                { value: "30", label: "Last 30 days" },
                { value: "90", label: "Last 90 days" },
              ]}
            />
            <FilterPill
              label="Category"
              value={cat}
              onChange={setCat}
              options={[
                { value: "all", label: "All", count: all.length },
                { value: "kids", label: "Children's", count: kids },
                { value: "other", label: "General", count: all.length - kids },
              ]}
            />
            <FilterPill
              label="IDs"
              value={fine}
              onChange={setFine}
              options={[
                { value: "all", label: "All" },
                { value: "fine", label: "Fine print only", count: hasField ? buried : undefined },
              ]}
            />
          </div>
        </Toolbar>
        <DataTable
          caption="CPSC recalls"
          rows={rows}
          columns={columns}
          rowKey={(r) => r.recall_number}
          rowLabel={(r) => `Open recall ${r.recall_number}: ${shortTitle(r.title)}`}
          onRowOpen={(r) => setOpen(r.recall_number)}
          selectedKey={openId}
          loading={recalls.loading}
          initialSort={{ id: "date", dir: "desc" }}
          pageSize={12}
          empty={
            <EmptyState icon={RiFileSearchLine} title="No recalls match">
              Nothing for “{q}” with these filters. Try a model number like <span className="rd-mono">TL1302Z</span>.
            </EmptyState>
          }
        />
      </Card>
      {!hasField && !recalls.loading && <p className="mt-3 text-caption-1-regular text-text-tertiary">* 73 of 151: the identifier appears in the description but not the title or product name (verified count, docs/charts/README.md).</p>}

      <RecallDrawer r={selected} onClose={() => setOpen(null)} />
    </Page>
  );
}

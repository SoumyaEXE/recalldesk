"use client";

import { RiExternalLinkLine, RiMapPin2Line, RiArchiveStackLine, RiShieldFlashLine, RiToolsLine } from "@remixicon/react";
import { useState, type ReactNode } from "react";
import { ButtonLink } from "@/components/base/buttons/button";
import { Drawer } from "@/components/ui/overlay";
import { ChildrensPill, Eyebrow, IdChip, IconTile, KeyValue, VerdictPill } from "@/components/ui/surface";
import type { InventoryRow } from "@/lib/api";
import { formatDate, shortTitle, soldWindow } from "@/lib/format";
import { idHit } from "@/lib/match";
import type { RecallRecord, Verdict } from "@/lib/types";
import { CorrectThis } from "./correct-form";
import { HighlightIds } from "./ids";
import { RecallImage } from "./recall-image";

export interface FlaggedItem {
  label: string;
  verdict: Verdict;
  recall_number: string;
  recall_title?: string;
  why?: string;
  look_for?: string | null;
  remedy?: string;
  inv?: InventoryRow;
}

export function recallIds(r?: RecallRecord): string[] {
  if (!r) return [];
  return [...new Set([...(r.spec?.model_numbers ?? []), ...(r.spec?.other_identifiers ?? []), ...(r.spec?.upcs ?? []), ...r.regex_ids, ...r.upcs])];
}

function Section({ icon, title, children, tone = "gray" }: { icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>; title: string; children: ReactNode; tone?: "gray" | "red" | "amber" | "blue" | "green" }) {
  return (
    <section className="flex gap-3">
      <IconTile icon={icon} tone={tone} size="sm" />
      <div className="flex min-w-0 flex-1 flex-col gap-1 pt-1">
        <h3 className="text-body-2-semibold text-text-primary">{title}</h3>
        <div className="text-body-2-regular text-text-secondary">{children}</div>
      </div>
    </section>
  );
}

export function ItemDrawer({ item: current, recall, shopId, onClose, totalRecalls }: { item: FlaggedItem | null; recall?: RecallRecord; shopId: string; onClose: () => void; totalRecalls?: number }) {
  // Keep the last item while the drawer animates out.
  const [kept, setKept] = useState(current);
  if (current && current !== kept) setKept(current);
  const item = current ?? kept;
  const ids = recallIds(recall);
  const text = item ? [item.label, item.inv?.name, item.inv?.brand, item.inv?.model, item.inv?.notes].filter(Boolean).join(" ") : "";
  const found = item ? idHit(ids, text) : [];
  const lookFor = item?.look_for ?? recall?.spec?.look_for ?? null;
  const remedy = item?.remedy ?? recall?.spec?.remedy_short ?? recall?.remedies[0];
  return (
    <Drawer
      isOpen={!!current}
      onOpenChange={(o) => !o && onClose()}
      width="lg"
      title={item?.inv?.name ?? item?.label ?? ""}
      subtitle={
        item && (
          <span className="flex flex-wrap items-center gap-2">
            <VerdictPill verdict={item.verdict} />
            {item.recall_number && <span className="rd-mono text-text-secondary">CPSC #{item.recall_number}</span>}
            {recall?.is_childrens && <ChildrensPill size="sm" />}
          </span>
        )
      }
      footer={
        recall && (
          <ButtonLink href={recall.url} target="_blank" rel="noreferrer" variant="secondary" size="small" trailingIcon={RiExternalLinkLine}>
            Read on cpsc.gov
          </ButtonLink>
        )
      }
    >
      {item && item.verdict === "no_match" && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-3 rounded-xl border border-line bg-card p-4">
            <Eyebrow>Your item</Eyebrow>
            <p className="text-body-semibold text-text-primary">{item.inv?.name ?? item.label}</p>
            <dl className="divide-y divide-line">
              {item.inv?.brand && <KeyValue k="Brand">{item.inv.brand}</KeyValue>}
              <KeyValue k="Model">{item.inv?.model ? <IdChip tone="gray">{item.inv.model}</IdChip> : <span className="text-text-tertiary">Not on the tag</span>}</KeyValue>
              {item.inv?.sku && <KeyValue k="SKU"><span className="rd-mono">{item.inv.sku}</span></KeyValue>}
              {item.inv?.category && <KeyValue k="Category">{item.inv.category}</KeyValue>}
              {item.inv?.price && <KeyValue k="Price"><span className="tabular-nums">{item.inv.price}</span></KeyValue>}
              {item.inv?.notes && <KeyValue k="Notes">{item.inv.notes}</KeyValue>}
            </dl>
          </div>
          <Section icon={RiShieldFlashLine} title="No recall matched" tone="green">
            Checked against {totalRecalls ? `all ${totalRecalls}` : "every"} CPSC recalls since July 18 (and children&apos;s recalls back to 2023 for kids&apos; shops). Nothing with this brand and product line, or with this model number, is recalled.
          </Section>
          <Section icon={RiMapPin2Line} title="Still worth a glance" tone="blue">
            Keep a photo of the label with the listing. If CPSC posts a recall for it later, next Thursday&apos;s sweep will flag it.
          </Section>
        </div>
      )}
      {item && item.verdict !== "no_match" && (
        <div className="flex flex-col gap-6">
          {/* Item vs recall */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-card p-4">
              <Eyebrow>Your item</Eyebrow>
              <div className="flex items-start gap-3">
                <span className="flex size-16 shrink-0 items-center justify-center rounded-lg border border-line bg-subtle" aria-hidden>
                  <RiArchiveStackLine className="size-6 text-foreground-icon-tertiary" />
                </span>
                <div className="min-w-0">
                  <p className="text-body-2-semibold text-text-primary">{item.inv?.name ?? item.label}</p>
                  <p className="text-caption-1-regular text-text-tertiary">{[item.inv?.brand, item.inv?.category].filter(Boolean).join(" · ") || "From your list"}</p>
                </div>
              </div>
              <dl className="divide-y divide-line">
                {item.inv && <KeyValue k="Model">{item.inv.model ? <IdChip tone={found.length ? "amber" : "gray"}>{item.inv.model}</IdChip> : <span className="text-text-tertiary">Not on the tag</span>}</KeyValue>}
                {item.inv?.sku && <KeyValue k="SKU"><span className="rd-mono">{item.inv.sku}</span></KeyValue>}
                {item.inv?.price && <KeyValue k="Price"><span className="tabular-nums">{item.inv.price}</span></KeyValue>}
                {item.inv?.notes && <KeyValue k="Notes">{item.inv.notes}</KeyValue>}
              </dl>
            </div>
            <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-card p-4">
              <Eyebrow>Recalled product</Eyebrow>
              <div className="flex items-start gap-3">
                <RecallImage src={recall?.images[0]} label={recall?.spec?.product_type ?? "recalled product"} size={64} />
                <div className="min-w-0">
                  <p className="text-body-2-semibold text-text-primary">{recall?.spec?.product_name ?? (item.recall_title ? shortTitle(item.recall_title) : `Recall ${item.recall_number}`)}</p>
                  <p className="text-caption-1-regular text-text-tertiary">{[recall?.spec?.brand, recall && formatDate(recall.recall_date)].filter(Boolean).join(" · ")}</p>
                </div>
              </div>
              <dl className="divide-y divide-line">
                <KeyValue k="Model nos.">
                  {recall?.spec?.model_numbers.length ? (
                    <span className="flex flex-wrap gap-1">
                      {recall.spec.model_numbers.slice(0, 6).map((m) => (
                        <IdChip key={m} tone={found.includes(m) ? "amber" : "gray"}>
                          {m}
                        </IdChip>
                      ))}
                    </span>
                  ) : (
                    <span className="text-text-tertiary">None stated</span>
                  )}
                </KeyValue>
                <KeyValue k="Sold">{recall?.spec ? soldWindow(recall.spec.sold_from, recall.spec.sold_to) : "—"}</KeyValue>
                {recall?.units && <KeyValue k="Units">{recall.units}</KeyValue>}
              </dl>
            </div>
          </div>

          <div className="flex flex-col gap-5">
            <Section icon={RiShieldFlashLine} title={item.verdict === "match" ? "Why it's a match" : "Why it needs a look"} tone={item.verdict === "match" ? "red" : "amber"}>
              {item.why ?? (item.verdict === "check" ? "Same brand and product line as the recall, but the item text doesn't show what decides it (model number, date code or sold window)." : "—")}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-caption-1-medium text-text-tertiary">Identifiers found:</span>
                {found.length ? found.map((f) => <IdChip key={f}>{f}</IdChip>) : <span className="text-caption-1-regular text-text-tertiary">none in the item text</span>}
              </div>
            </Section>
            <Section icon={RiMapPin2Line} title="Where to look" tone="blue">
              {lookFor ? <HighlightIds text={lookFor} /> : "Brand and model on the product label."}
            </Section>
            <Section icon={RiToolsLine} title="Remedy" tone="green">
              {remedy ?? "See the CPSC notice."}
              {recall?.spec?.hazard_short && <p className="mt-1 text-caption-1-regular text-text-tertiary">Hazard: {recall.spec.hazard_short}</p>}
            </Section>
          </div>

          <div className="rounded-xl border border-dashed border-line-strong p-4">
            <p className="mb-1 text-body-2-semibold text-text-primary">Not a match?</p>
            <p className="mb-3 text-caption-1-regular text-text-tertiary">Correct it once. RecallDesk saves it as a Backboard memory for this shop and applies it every Thursday after.</p>
            <CorrectThis key={`${item.label}-${item.recall_number}`} item={item.label} recallNumber={item.recall_number} current={item.verdict} shopId={shopId} />
          </div>
        </div>
      )}
    </Drawer>
  );
}

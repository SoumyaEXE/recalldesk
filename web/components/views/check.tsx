"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { RiFileUploadLine, RiPlayLine, RiPrinterLine, RiRefreshLine, RiSparklingLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Chip } from "@/components/base/badges/chip";
import { Page, PageHeader, Panel } from "@/components/rd/app-shell";
import { RecallCard } from "@/components/rd/recall-card";
import { StepTimeline } from "@/components/rd/step-timeline";
import { getCardStatus, isSimulated, startCheck } from "@/lib/api";
import { parseItems } from "@/lib/match";
import type { CardStatus } from "@/lib/types";
import { cx } from "@/utils/cx";

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

const POLL_MS = 900;

export function CheckView() {
  const [text, setText] = useState("");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [status, setStatus] = useState<CardStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const items = useMemo(() => parseItems(text), [text]);

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
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [workflowId]);

  const run = async () => {
    if (!items.length) return;
    setStarting(true);
    setError(null);
    setStatus(null);
    const r = await startCheck(items);
    setStarting(false);
    setWorkflowId(r.workflow_id);
  };

  const done = status?.status === "completed";
  const running = !!workflowId && !done && status?.status !== "failed";

  return (
    <Page wide>
      <PageHeader
        eyebrow="On demand · InventoryCheckWorkflow"
        title="Check items before you list them"
        description="Paste one item per line, or upload a CSV (name, brand, model, notes). Each item is matched against every CPSC recall since July 18, and you get a printable card."
        actions={
          done ? (
            <Button leadingIcon={RiPrinterLine} onClick={() => window.print()}>
              Print card
            </Button>
          ) : undefined
        }
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <div className="rd-no-print flex min-w-0 flex-col gap-4">
          <Panel
            title="Your items"
            description={items.length ? `${items.length} item${items.length === 1 ? "" : "s"} ready` : "One per line, or CSV with a header row"}
            actions={
              <Button size="small" variant="ghost" leadingIcon={RiSparklingLine} onClick={() => setText(SAMPLE)}>
                Use sample
              </Button>
            }
          >
            <div className="flex flex-col gap-3">
              <label htmlFor="items" className="sr-only">
                Items to check
              </label>
              <textarea
                id="items"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={12}
                spellCheck={false}
                wrap="off"
                placeholder={"Graco Pack 'n Play, gray\nSkip Hop Elmo teether 9R263210\nMelissa & Doug fire truck\n…"}
                className="w-full resize-y rounded-xl border border-border-button-default bg-background-primary-default px-3 py-2.5 font-mono text-body-2-regular text-text-primary outline-none placeholder:text-text-placeholder hover:border-border-button-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
              />
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                className="sr-only"
                aria-label="Upload CSV"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  const t = await f.text();
                  const first = t.split(/\r?\n/)[0]?.toLowerCase() ?? "";
                  setText(f.name.endsWith(".csv") && !first.includes("name") ? `name,brand,model,notes\n${t}` : t);
                  e.target.value = "";
                }}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button leadingIcon={RiPlayLine} onClick={run} disabled={!items.length || starting || running}>
                  {starting ? "Starting…" : running ? "Checking…" : `Check ${items.length || ""} item${items.length === 1 ? "" : "s"}`.replace("  ", " ")}
                </Button>
                <Button variant="secondary" leadingIcon={RiFileUploadLine} onClick={() => fileRef.current?.click()}>
                  Upload CSV
                </Button>
              </div>
              {items.length > 0 && (
                <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto rounded-xl bg-background-secondary-default p-2" aria-label="Parsed items">
                  {items.slice(0, 50).map((it, i) => (
                    <li key={i} className="flex min-w-0 items-baseline gap-2 text-caption-1-regular">
                      <span className="w-5 shrink-0 text-end font-mono text-text-tertiary rd-num">{i + 1}</span>
                      <span className="truncate text-text-primary">{it.name}</span>
                      {it.brand && <span className="shrink-0 text-text-secondary">{it.brand}</span>}
                      {it.model && <code className="shrink-0 font-mono text-text-tertiary">{it.model}</code>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>

          {workflowId && (
            <Panel
              title="Workflow progress"
              description={<span className="font-mono text-caption-1-regular break-all">{workflowId}</span>}
              actions={
                isSimulated(workflowId) ? (
                  <Chip variant="caption" color="yellow">
                    Simulated in browser (API offline)
                  </Chip>
                ) : (
                  <Chip variant="caption" color="blue">
                    Temporal
                  </Chip>
                )
              }
            >
              {status ? <StepTimeline steps={status.steps} /> : <p className="text-body-2-regular text-text-tertiary">Starting workflow…</p>}
              {error && <p className="mt-3 text-caption-1-regular text-text-error-primary">{error}</p>}
            </Panel>
          )}
        </div>

        <div className="min-w-0">
          {done && status?.card ? (
            <div className="flex flex-col gap-3">
              <RecallCard card={status.card} correctable className="rd-rise" />
              <div className="rd-no-print flex flex-wrap items-center gap-2 text-caption-1-regular text-text-tertiary">
                <span>Corrections are saved as shop memories and applied next time.</span>
                <Button size="small" variant="ghost" leadingIcon={RiRefreshLine} onClick={run}>
                  Re-run with corrections
                </Button>
              </div>
            </div>
          ) : (
            <div className={cx("rd-no-print rd-ruled flex min-h-[420px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border-button-hover px-6 py-16 text-center")}>
              <p className="rd-notice text-[26px] text-text-primary">{running ? "Checking your items…" : "Your card shows up here"}</p>
              <p className="max-w-[420px] text-body-2-regular text-text-secondary">
                {running
                  ? "Each step is a Temporal activity: retried on bad model output, resumed if a worker dies."
                  : "DO NOT SELL for items that are the recalled product. CHECK LABEL when the label decides it, with exactly where to look."}
              </p>
            </div>
          )}
        </div>
      </div>
    </Page>
  );
}

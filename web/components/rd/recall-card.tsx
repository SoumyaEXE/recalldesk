import { RiBrainLine } from "@remixicon/react";
import { formatDate, shortTitle } from "@/lib/format";
import type { RecallCard as Card } from "@/lib/types";
import { cx } from "@/utils/cx";
import { CorrectThis } from "./correct-form";
import { HighlightIds } from "./ids";
import { VerdictGlyph } from "./verdict";

const cpscUrl = (n: string) => `https://www.cpsc.gov/Recalls?search_api_fulltext=${encodeURIComponent(n)}`;

function RecallRef({ n, title }: { n: string; title?: string }) {
  return (
    <a
      href={cpscUrl(n)}
      target="_blank"
      rel="noreferrer"
      className="inline-flex max-w-full items-baseline gap-1.5 rounded text-caption-1-regular text-paper-ink-3 outline-none hover:text-paper-ink-2 focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <span className="shrink-0 font-mono font-semibold text-paper-ink-2">CPSC #{n}</span>
      {title && <span className="truncate">{shortTitle(title)}</span>}
    </a>
  );
}

function Band({ tone, count, title, sub }: { tone: "stop" | "caution"; count: number; title: string; sub: string }) {
  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 sm:px-6",
        tone === "stop" ? "bg-stop-solid text-white" : "bg-caution-solid text-caution-ink",
      )}
    >
      <VerdictGlyph verdict={tone === "stop" ? "match" : "check"} inverse className="size-6" />
      <h3 className="rd-notice text-[22px] leading-7 sm:text-[26px]">{title}</h3>
      <span className={cx("rd-figure rounded-md px-1.5 py-0.5 text-[18px]", tone === "stop" ? "bg-white/20" : "bg-black/10")}>{count}</span>
      <span className={cx("text-caption-1-semibold sm:ms-auto", tone === "stop" ? "text-white/90" : "text-caution-ink/80")}>{sub}</span>
    </div>
  );
}

export function RecallCard({ card, correctable = false, className }: { card: Card; correctable?: boolean; className?: string }) {
  const empty = card.do_not_sell.length === 0 && card.check_label.length === 0;
  return (
    <article
      aria-label={`Recall check for ${card.shop_name}, week of ${formatDate(card.week_of)}`}
      className={cx("rd-paper-scope rd-print-card relative overflow-hidden rounded-2xl border border-paper-rule bg-paper shadow-card", className)}
    >
      <div className="rd-tape h-1.5" aria-hidden />
      {/* Header */}
      <header className="rd-ruled flex flex-col gap-3 border-b border-paper-rule px-4 pt-4 pb-4 sm:flex-row sm:items-end sm:justify-between sm:px-6 sm:ps-14">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="rd-eyebrow text-paper-ink-3">Recall check · intake desk notice</p>
          <h2 className="rd-notice text-[28px] leading-8 text-paper-ink sm:text-[34px] sm:leading-9">{card.shop_name}</h2>
          <p className="text-body-2-medium text-paper-ink-2">
            Week of <span className="font-semibold text-paper-ink">{formatDate(card.week_of, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</span>
          </p>
        </div>
        <dl className="grid shrink-0 grid-cols-2 gap-x-5 gap-y-1 sm:text-end">
          <div>
            <dt className="text-caption-1-medium text-paper-ink-3">New CPSC recalls</dt>
            <dd className="rd-figure text-[30px] text-paper-ink">{card.new_recalls}</dd>
          </div>
          <div>
            <dt className="text-caption-1-medium text-paper-ink-3">Items checked</dt>
            <dd className="rd-figure text-[30px] text-paper-ink">{card.items_checked}</dd>
          </div>
        </dl>
      </header>

      {empty && (
        <div className="flex items-center gap-3 px-6 py-8">
          <VerdictGlyph verdict="no_match" className="size-8" />
          <div>
            <p className="rd-notice text-[22px] text-paper-ink">All clear this week</p>
            <p className="text-body-2-regular text-paper-ink-2">None of the items checked match a recall. Keep the label photos anyway.</p>
          </div>
        </div>
      )}

      {/* DO NOT SELL */}
      {card.do_not_sell.length > 0 && (
        <section aria-label="Do not sell">
          <Band tone="stop" count={card.do_not_sell.length} title="Do not sell" sub="Pull from the floor. Don't list, donate or return to the consignor." />
          <ol className="divide-y divide-paper-rule">
            {card.do_not_sell.map((r, i) => (
              <li key={`${r.recall_number}-${i}`} className="grid grid-cols-[20px_minmax(0,1fr)] gap-x-3 gap-y-1 px-4 py-3 sm:grid-cols-[20px_minmax(0,1fr)_minmax(0,0.9fr)] sm:px-6">
                <span className="mt-0.5 size-4 rounded-[3px] border-2 border-paper-ink-2" aria-hidden title="Tick when pulled" />
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="text-body-semibold text-paper-ink">{r.item}</p>
                  <RecallRef n={r.recall_number} title={r.recall_title} />
                  {correctable && <CorrectThis item={r.item} recallNumber={r.recall_number} current="match" shopId={card.shop_id} />}
                </div>
                <dl className="col-start-2 flex min-w-0 flex-col gap-1 text-body-2-regular sm:col-start-3">
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 font-semibold text-stop-text">Why</dt>
                    <dd className="text-paper-ink">{r.why}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt className="shrink-0 font-semibold text-paper-ink-2">Remedy</dt>
                    <dd className="text-paper-ink-2">{r.remedy}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* CHECK LABEL */}
      {card.check_label.length > 0 && (
        <section aria-label="Check label">
          <Band tone="caution" count={card.check_label.length} title="Check label" sub="Look before you list. Clear it only if the label doesn't match." />
          <ol className="divide-y divide-paper-rule">
            {card.check_label.map((r, i) => (
              <li key={`${r.recall_number}-${i}`} className="grid grid-cols-[20px_minmax(0,1fr)] gap-x-3 gap-y-1 px-4 py-3 sm:grid-cols-[20px_minmax(0,1fr)_minmax(0,0.9fr)] sm:px-6">
                <span className="mt-0.5 size-4 rounded-[3px] border-2 border-paper-ink-2" aria-hidden title="Tick when checked" />
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="text-body-semibold text-paper-ink">{r.item}</p>
                  <RecallRef n={r.recall_number} title={r.recall_title} />
                  {correctable && <CorrectThis item={r.item} recallNumber={r.recall_number} current="check" shopId={card.shop_id} />}
                </div>
                <div className="col-start-2 flex min-w-0 gap-1.5 text-body-2-regular sm:col-start-3">
                  <span className="shrink-0 font-semibold text-caution-text">Look for</span>
                  <span className="text-paper-ink">{r.look_for ? <HighlightIds text={r.look_for} /> : "Brand and model on the product label"}</span>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Memories */}
      {card.applied_memories.length > 0 && (
        <section aria-label="Shop memories applied" className="flex flex-col gap-2 border-t border-paper-rule px-4 py-3 sm:px-6">
          <p className="flex items-center gap-1.5 text-caption-1-semibold text-paper-ink-2">
            <RiBrainLine className="size-3.5" aria-hidden /> Your shop&apos;s notes, applied this week
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {card.applied_memories.map((m) => (
              <li key={m.memory_id} className="flex max-w-full items-start gap-1.5 rounded-lg border border-paper-rule bg-white/60 px-2 py-1 text-caption-1-regular text-paper-ink-2">
                <code className="shrink-0 font-mono text-caption-2-medium text-paper-ink-3">{m.memory_id}</code>
                <span className="min-w-0">{m.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Sign-off + footer */}
      <footer className="flex flex-col gap-3 border-t-2 border-dashed border-paper-rule px-4 py-3 sm:px-6">
        <div className="grid grid-cols-2 gap-4 text-caption-1-medium text-paper-ink-3 sm:grid-cols-3">
          <span className="flex items-end gap-2">
            Pulled by <span className="h-4 flex-1 border-b border-paper-ink-3" />
          </span>
          <span className="flex items-end gap-2">
            Date <span className="h-4 flex-1 border-b border-paper-ink-3" />
          </span>
          <span className="col-span-2 flex items-end gap-2 sm:col-span-1">
            Initials <span className="h-4 flex-1 border-b border-paper-ink-3" />
          </span>
        </div>
        <div className="flex flex-col gap-1 text-caption-2-regular text-paper-ink-3 sm:flex-row sm:items-center sm:justify-between">
          <span>
            RecallDesk · <span className="font-mono">{card.model}</span> · <span className="font-mono">{card.workflow_id}</span>
          </span>
          <span>Not legal advice. We read the text, not your labels. Source: cpsc.gov/Recalls</span>
        </div>
      </footer>
    </article>
  );
}

"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Page, PageHeader, Panel, Stat } from "@/components/rd/app-shell";
import { PlaceholderNote } from "@/components/rd/data-source-chip";
import { VerdictBadge } from "@/components/rd/verdict";
import { getEval } from "@/lib/api";
import { formatDate, frac, pct, usd } from "@/lib/format";
import type { Confusion, EvalModel, EvalResults, Verdict } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

const ROLE_LABEL: Record<string, string> = {
  lora: "Qwen3.5-4B + LoRA (ours)",
  teacher: "Teacher · Qwen3.5-397B",
  base: "Qwen3.5-4B base",
  base_guided: "Qwen3.5-4B base, guided JSON",
  heuristic: "Identifier rules (regex)",
};
const roleLabel = (m: EvalModel) => (m.role.startsWith("backboard:") ? `${m.name}` : (ROLE_LABEL[m.role] ?? m.name));
const ORDER = ["lora", "teacher", "base_guided", "base", "heuristic"];
const rank = (r: string) => (ORDER.indexOf(r) === -1 ? 50 : ORDER.indexOf(r));

/* ----- accuracy with 95% CI: dot + whisker, ours highlighted ---------------- */
function AccuracyCI({ models }: { models: EvalModel[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const lo = Math.max(0, Math.floor((Math.min(...models.map((m) => m.acc_ci[0])) - 0.05) * 10) / 10);
  const hi = 1;
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const ticks = Array.from({ length: Math.round((hi - lo) * 10) + 1 }, (_, i) => +(lo + i * 0.1).toFixed(1));
  return (
    <div className="flex flex-col gap-1" role="img" aria-label="Accuracy with 95% bootstrap confidence intervals per model">
      {models.map((m) => {
        const ours = m.role === "lora";
        const on = hover === m.role;
        return (
          <div
            key={m.role}
            className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_56px] items-center gap-3 rounded-lg px-1 py-1.5 sm:grid-cols-[220px_minmax(0,1fr)_64px]"
            onMouseEnter={() => setHover(m.role)}
            onMouseLeave={() => setHover(null)}
          >
            <span className={cx("truncate text-caption-1-medium sm:text-body-2-medium", ours ? "text-text-primary" : "text-text-secondary")}>{roleLabel(m)}</span>
            <span className="relative h-6">
              {ticks.map((t) => (
                <span key={t} className="absolute inset-y-0 w-px bg-separator-border" style={{ left: x(t) }} aria-hidden />
              ))}
              <span
                className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full"
                style={{ left: x(m.acc_ci[0]), width: `calc(${x(m.acc_ci[1])} - ${x(m.acc_ci[0])})`, background: ours ? "var(--rd-m-ours)" : "var(--rd-m-other)", opacity: 0.45 }}
              />
              <span
                className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-background-primary-default"
                style={{ left: x(m.acc), background: ours ? "var(--rd-m-ours)" : "var(--rd-m-other)" }}
              />
              {on && (
                <span className="absolute -top-8 z-10 -translate-x-1/2 rounded-md border border-border-button-default bg-background-primary-default px-2 py-1 font-mono text-caption-1-medium whitespace-nowrap text-text-primary shadow-md" style={{ left: x(m.acc) }}>
                  {pct(m.acc, 1)} · CI {pct(m.acc_ci[0], 1)}–{pct(m.acc_ci[1], 1)}
                </span>
              )}
            </span>
            <span className={cx("text-end font-mono text-body-2-semibold rd-num", ours ? "text-ink" : "text-text-secondary")}>{pct(m.acc, 1)}</span>
          </div>
        );
      })}
      <div className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_56px] gap-3 px-1 sm:grid-cols-[220px_minmax(0,1fr)_64px]" aria-hidden>
        <span />
        <span className="relative h-4 font-mono text-caption-2-regular text-text-tertiary">
          {ticks.map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: x(t) }}>
              {Math.round(t * 100)}%
            </span>
          ))}
        </span>
        <span />
      </div>
    </div>
  );
}

/* ----- confusion matrix (sequential single hue, row-normalised) ------------- */
const VLABEL: Record<Verdict, string> = { match: "match", check: "check", no_match: "no match" };
function ConfusionGrid({ name, c }: { name: string; c?: Confusion }) {
  if (!c?.labels?.length) return <p className="text-body-2-regular text-text-tertiary">{name}: not available yet.</p>;
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="text-body-2-semibold text-text-primary">{name}</figcaption>
      <table className="w-full table-fixed border-separate border-spacing-0.5 text-caption-1-medium">
        <thead>
          <tr>
            <th className="w-[72px] text-start text-caption-2-medium text-text-tertiary">gold ↓ / model →</th>
            {c.labels.map((l) => (
              <th key={l} scope="col" className="pb-1 text-center font-mono text-text-secondary">
                {VLABEL[l]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {c.matrix.map((row, i) => {
            const total = row.reduce((a, b) => a + b, 0) || 1;
            return (
              <tr key={i}>
                <th scope="row" className="pe-1 text-start font-mono text-text-secondary">
                  {VLABEL[c.labels[i]]}
                </th>
                {row.map((v, j) => {
                  const share = v / total;
                  return (
                    <td
                      key={j}
                      title={`gold ${VLABEL[c.labels[i]]}, model ${VLABEL[c.labels[j]]}: ${v} (${pct(share)})`}
                      className={cx("h-12 rounded-md text-center font-mono text-body-2-semibold rd-num", share > 0.5 ? "text-white" : "text-text-primary", i === j && "ring-1 ring-border-button-hover")}
                      style={{ background: `color-mix(in oklab, var(--rd-seq) ${Math.round(8 + share * 85)}%, var(--color-background-primary-default))` }}
                    >
                      {v}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </figure>
  );
}

/* ----- training loss --------------------------------------------------------- */
function LossChart({ t }: { t: EvalResults["training"] }) {
  const data = useMemo(() => {
    const m = new Map<number, { step: number; train?: number; test?: number }>();
    t.loss_curve.forEach(([s, v]) => m.set(s, { ...(m.get(s) ?? { step: s }), train: v }));
    t.test_nll.forEach(([s, v]) => m.set(s, { ...(m.get(s) ?? { step: s }), test: v }));
    return [...m.values()].sort((a, b) => a.step - b.step);
  }, [t]);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-4 text-caption-1-medium text-text-secondary" aria-hidden>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded" style={{ background: "var(--rd-series-1)" }} /> Train loss
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: "var(--rd-series-2)" }} /> Test NLL (held-out recalls)
        </span>
      </div>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--color-separator-border)" />
            <XAxis dataKey="step" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 11, fill: "var(--color-text-tertiary)" }} tickLine={false} axisLine={{ stroke: "var(--color-separator-border)" }} />
            <YAxis tick={{ fontSize: 11, fill: "var(--color-text-tertiary)" }} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              contentStyle={{ background: "var(--color-background-primary-default)", border: "1px solid var(--color-border-button-default)", borderRadius: 10, fontSize: 12 }}
              labelFormatter={(s) => `step ${s}`}
              formatter={(v, n) => [typeof v === "number" ? v.toFixed(3) : String(v), n === "train" ? "train loss" : "test NLL"]}
            />
            <Line type="monotone" dataKey="train" stroke="var(--rd-series-1)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="test" stroke="var(--rd-series-2)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--color-background-primary-default)", fill: "var(--rd-series-2)" }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Fraction({ s, good }: { s: string; good: "high" | "low" }) {
  const [a, b] = frac(s);
  const r = b ? a / b : 0;
  return (
    <span className="flex flex-col items-end">
      <span className="font-mono text-body-2-semibold text-text-primary rd-num">{s}</span>
      <span className={cx("font-mono text-caption-2-regular rd-num", good === "high" ? "text-text-tertiary" : "text-text-tertiary")}>{pct(r)}</span>
    </span>
  );
}

export function LabView() {
  const { data, loading, placeholder } = useLoad(getEval, "eval");
  const models = useMemo(() => [...(data?.models ?? [])].sort((a, b) => rank(a.role) - rank(b.role)), [data]);
  const lora = models.find((m) => m.role === "lora");
  const teacher = models.find((m) => m.role === "teacher");
  const label = (role: string) => {
    const m = models.find((x) => x.role === role);
    return m ? roleLabel(m) : role;
  };

  return (
    <Page wide>
      <PageHeader
        eyebrow="Model Lab · Tinker LoRA"
        title="The big model teaches, the small model reads"
        description={
          data
            ? `${data.test_size} held-out (recall, listing) pairs from recalls the student never saw in training, graded by ${data.gold} labels. 10,000-sample bootstrap CIs; exact McNemar on discordant pairs.`
            : "Loading evaluation…"
        }
        actions={<PlaceholderNote show={placeholder}>{data?.note ? "Placeholder: awaiting real eval" : "Placeholder numbers"}</PlaceholderNote>}
      />

      {loading || !data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-[320px] animate-pulse rounded-2xl bg-background-secondary-default" />
          <div className="h-[320px] animate-pulse rounded-2xl bg-background-secondary-default" />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="LoRA accuracy" value={lora ? pct(lora.acc, 1) : "—"} tone="ink" hint={lora ? `CI ${pct(lora.acc_ci[0])}–${pct(lora.acc_ci[1])}` : undefined} />
            <Stat label="Risky caught" value={lora?.risky_caught ?? "—"} hint="gold match or check" />
            <Stat label="False alarms" value={lora?.false_alarms ?? "—"} hint="flagged, gold no match" />
            <Stat label="Cost / 1k checks" value={lora ? usd(lora.cost_per_1k_usd) : "—"} hint={teacher ? `teacher ${usd(teacher.cost_per_1k_usd)}` : undefined} />
            <Stat label="p50 latency" value={lora ? `${lora.p50_latency_ms} ms` : "—"} hint={teacher ? `teacher ${teacher.p50_latency_ms} ms` : undefined} className="col-span-2 md:col-span-1" />
          </div>

          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
            <Panel title="Accuracy, with 95% CI" description="Exact-verdict accuracy vs blind human labels. Hover a row for the interval.">
              <AccuracyCI models={models} />
            </Panel>
            <Panel title="Training" description={`${data.training.base_model} · LoRA rank ${data.training.rank} · ${data.training.steps} steps · ${data.training.epochs} epochs · lr ${data.training.lr}`}>
              <LossChart t={data.training} />
            </Panel>
          </div>

          <Panel title="Every model, same test set" padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-body-2-regular">
                <thead>
                  <tr className="border-b border-separator-border text-caption-1-semibold text-text-tertiary">
                    <th className="px-4 py-2 text-start">Model</th>
                    <th className="px-3 py-2 text-end">Accuracy</th>
                    <th className="px-3 py-2 text-end">Macro F1</th>
                    <th className="px-3 py-2 text-end">Risky caught</th>
                    <th className="px-3 py-2 text-end">False alarms</th>
                    <th className="px-3 py-2 text-end">JSON valid</th>
                    <th className="px-3 py-2 text-end">p50 latency</th>
                    <th className="px-4 py-2 text-end">Cost / 1k</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.role} className={cx("border-b border-separator-border last:border-b-0", m.role === "lora" && "bg-background-secondary-default/70")}>
                      <th scope="row" className="px-4 py-2.5 text-start font-medium text-text-primary">
                        <span className="flex flex-col">
                          <span>{roleLabel(m)}</span>
                          <code className="font-mono text-caption-2-regular text-text-tertiary">{m.role}</code>
                        </span>
                      </th>
                      <td className="px-3 py-2.5 text-end font-mono text-body-2-semibold text-text-primary rd-num">{pct(m.acc, 1)}</td>
                      <td className="px-3 py-2.5 text-end font-mono text-text-secondary rd-num">{m.macro_f1.toFixed(3)}</td>
                      <td className="px-3 py-2.5">
                        <Fraction s={m.risky_caught} good="high" />
                      </td>
                      <td className="px-3 py-2.5">
                        <Fraction s={m.false_alarms} good="low" />
                      </td>
                      <td className="px-3 py-2.5 text-end font-mono text-text-secondary rd-num">{pct(m.json_valid)}</td>
                      <td className="px-3 py-2.5 text-end font-mono text-text-secondary rd-num">{m.p50_latency_ms.toLocaleString()} ms</td>
                      <td className="px-4 py-2.5 text-end font-mono text-text-secondary rd-num">{usd(m.cost_per_1k_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid items-start gap-4 xl:grid-cols-2">
            <Panel title="Paired tests" description="Same pairs, two models. Gain = accuracy(A) − accuracy(B). p from exact McNemar on the pairs only one got right." padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-body-2-regular">
                  <thead>
                    <tr className="border-b border-separator-border text-caption-1-semibold text-text-tertiary">
                      <th className="px-4 py-2 text-start">A vs B</th>
                      <th className="px-3 py-2 text-end whitespace-nowrap">Gain (95% CI)</th>
                      <th className="px-3 py-2 text-end">Only A / only B</th>
                      <th className="px-4 py-2 text-end">p</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.paired.map((p) => {
                      const sig = p.p < 0.05;
                      return (
                        <tr key={`${p.a}-${p.b}`} className="border-b border-separator-border last:border-b-0">
                          <th scope="row" className="px-4 py-2.5 text-start font-medium text-text-primary">
                            {label(p.a)} <span className="text-text-tertiary">vs</span> {label(p.b)}
                          </th>
                          <td className="px-3 py-2.5 text-end font-mono whitespace-nowrap rd-num">
                            <span className={cx("text-body-2-semibold", p.gain > 0 ? "text-ink" : "text-text-secondary")}>
                              {p.gain > 0 ? "+" : ""}
                              {(p.gain * 100).toFixed(1)} pts
                            </span>
                            <span className="block text-caption-2-regular text-text-tertiary">
                              [{(p.ci[0] * 100).toFixed(1)}, {(p.ci[1] * 100).toFixed(1)}]
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-end font-mono text-text-secondary rd-num">
                            {p.only_a} / {p.only_b}
                          </td>
                          <td className="px-4 py-2.5 text-end font-mono rd-num">
                            <span className={sig ? "font-semibold text-text-primary" : "text-text-tertiary"}>{p.p < 0.001 ? p.p.toExponential(1) : p.p.toFixed(3)}</span>
                            <span className="block text-caption-2-regular text-text-tertiary">{sig ? "significant" : "not significant"}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel title="Confusion: base vs LoRA" description="Rows are human gold labels; cell shade is the share of that row.">
              <div className="grid gap-5 sm:grid-cols-2">
                <ConfusionGrid name="Base 4B" c={data.confusion.base} />
                <ConfusionGrid name="LoRA 4B (ours)" c={data.confusion.lora} />
              </div>
            </Panel>
          </div>

          <Panel title="Before and after fine-tuning" description="Held-out pairs where the base model and the LoRA disagree." padded={false}>
            <ul className="divide-y divide-separator-border">
              {data.examples.map((e) => (
                <li key={e.pair_id} className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <p className="text-body-2-semibold text-text-primary">“{e.listing_title}”</p>
                    <p className="truncate text-caption-1-regular text-text-tertiary">vs {e.recall_title}</p>
                  </div>
                  <dl className="grid grid-cols-3 gap-2 md:w-[420px]">
                    {(
                      [
                        ["Human", e.gold],
                        ["Base", e.base],
                        ["LoRA", e.lora],
                      ] as const
                    ).map(([k, v]) => (
                      <div key={k} className="flex flex-col gap-1">
                        <dt className="text-caption-2-semibold text-text-tertiary">
                          {k}
                          {k !== "Human" && (v === e.gold ? " ✓" : " ✗")}
                        </dt>
                        <dd>
                          <VerdictBadge verdict={v} size="sm" short />
                        </dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
          </Panel>
          <p className="text-caption-1-regular text-text-tertiary">Generated {formatDate(data.generated_at)} · gold: {data.gold}</p>
        </div>
      )}
    </Page>
  );
}

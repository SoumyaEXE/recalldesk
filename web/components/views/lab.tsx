"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { RiCoinsLine, RiFlaskLine, RiLineChartLine, RiShieldCheckLine, RiSpeedLine, RiTimerFlashLine } from "@remixicon/react";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { KpiCard, KpiRow } from "@/components/ui/kpi";
import { Card, CardHeader, DemoBadge, EmptyState, Pill, Skeleton, VerdictPill } from "@/components/ui/surface";
import { getEval } from "@/lib/api";
import { formatDate, frac, pct, usd } from "@/lib/format";
import type { Confusion, EvalModel, EvalResults, Verdict } from "@/lib/types";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

type Model = Omit<EvalModel, "acc" | "acc_ci"> & { acc: number | null; acc_ci?: [number, number]; pending?: boolean; p95_latency_ms?: number; note?: string };

const ROLE_LABEL: Record<string, string> = {
  lora: "Qwen3.5-4B + LoRA (ours)",
  teacher: "Teacher · Qwen3.5-397B",
  base: "Qwen3.5-4B base",
  base_guided: "4B base + teacher's rulebook",
  heuristic: "Identifier rules (no model)",
};
const SHORT: Record<string, string> = { lora: "LoRA 4B", teacher: "Teacher 397B", base: "Base 4B", base_guided: "Guided 4B", heuristic: "Rules" };
const roleLabel = (m: { role: string; name: string }) => (m.role.startsWith("backboard:") ? m.name : (ROLE_LABEL[m.role] ?? m.name));
const short = (m: { role: string; name: string }) => SHORT[m.role] ?? m.name.slice(0, 14);
const ORDER = ["lora", "teacher", "base_guided", "base", "heuristic"];
const rank = (r: string) => (ORDER.indexOf(r) === -1 ? 50 : ORDER.indexOf(r));
const ready = (m: Model): m is Model & { acc: number; acc_ci: [number, number] } => typeof m.acc === "number" && !m.pending;

const AXIS = { fontSize: 11, fill: "var(--color-text-tertiary)" };
const TIP = {
  contentStyle: { background: "var(--rd-card)", border: "1px solid var(--rd-line)", borderRadius: 10, fontSize: 12, boxShadow: "0 8px 24px -12px rgb(16 24 40 / .25)" },
  labelStyle: { color: "var(--color-text-primary)", fontWeight: 600 },
  itemStyle: { color: "var(--color-text-secondary)" },
  cursor: { fill: "var(--rd-hover)" },
};

/* accuracy with 95% CI: dot + whisker, ours highlighted */
function AccuracyCI({ models }: { models: (Model & { acc: number; acc_ci: [number, number] })[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const lo = Math.max(0, Math.floor((Math.min(...models.map((m) => m.acc_ci[0])) - 0.05) * 10) / 10);
  const x = (v: number) => `${((v - lo) / (1 - lo)) * 100}%`;
  const ticks = Array.from({ length: Math.round((1 - lo) * 10) + 1 }, (_, i) => +(lo + i * 0.1).toFixed(1));
  return (
    <div className="flex flex-col gap-1" role="img" aria-label="Accuracy with 95% bootstrap confidence intervals per model">
      {models.map((m) => {
        const ours = m.role === "lora";
        return (
          <div key={m.role} className="grid grid-cols-[minmax(0,130px)_minmax(0,1fr)_52px] items-center gap-3 rounded-lg px-1 py-2 hover:bg-hover sm:grid-cols-[190px_minmax(0,1fr)_60px]" onMouseEnter={() => setHover(m.role)} onMouseLeave={() => setHover(null)}>
            <span className={cx("truncate text-caption-1-medium sm:text-body-2-medium", ours ? "text-text-primary" : "text-text-secondary")}>{roleLabel(m)}</span>
            <span className="relative h-6">
              {ticks.map((t) => (
                <span key={t} className="absolute inset-y-0 w-px bg-line" style={{ left: x(t) }} aria-hidden />
              ))}
              <span className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full" style={{ left: x(m.acc_ci[0]), width: `calc(${x(m.acc_ci[1])} - ${x(m.acc_ci[0])})`, background: "var(--rd-series-1)", opacity: ours ? 0.55 : 0.3 }} />
              <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card" style={{ left: x(m.acc), background: ours ? "var(--rd-m-ours)" : "var(--rd-series-1)" }} />
              {hover === m.role && (
                <span className="absolute -top-8 z-10 -translate-x-1/2 rounded-md border border-line bg-card px-2 py-1 text-caption-1-medium whitespace-nowrap text-text-primary shadow-pop" style={{ left: x(m.acc) }}>
                  {pct(m.acc, 1)} · CI {pct(m.acc_ci[0], 1)}–{pct(m.acc_ci[1], 1)}
                </span>
              )}
            </span>
            <span className="text-end text-body-2-semibold text-text-primary tabular-nums">{pct(m.acc, 1)}</span>
          </div>
        );
      })}
      <div className="grid grid-cols-[minmax(0,130px)_minmax(0,1fr)_52px] gap-3 px-1 sm:grid-cols-[190px_minmax(0,1fr)_60px]" aria-hidden>
        <span />
        <span className="relative h-4 text-caption-2-regular text-text-tertiary">
          {ticks.map((t, i) => (
            <span key={t} className={cx("absolute -translate-x-1/2 tabular-nums", i % 2 === 1 && "hidden sm:inline")} style={{ left: x(t) }}>
              {Math.round(t * 100)}%
            </span>
          ))}
        </span>
        <span />
      </div>
    </div>
  );
}

const VLABEL: Record<Verdict, string> = { match: "match", check: "check", no_match: "no match" };
function ConfusionGrid({ name, c }: { name: string; c?: Confusion }) {
  if (!c?.labels?.length) return null;
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="text-body-2-semibold text-text-primary">{name}</figcaption>
      <table className="w-full table-fixed border-separate border-spacing-0.5 text-caption-1-medium">
        <thead>
          <tr>
            <th className="w-[64px] text-start text-caption-2-medium text-text-tertiary">key ↓</th>
            {c.labels.map((l) => (
              <th key={l} scope="col" className="pb-1 text-center text-caption-2-medium text-text-tertiary">
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
                <th scope="row" className="pe-1 text-start text-caption-2-medium text-text-tertiary">
                  {VLABEL[c.labels[i]]}
                </th>
                {row.map((v, j) => {
                  const share = v / total;
                  return (
                    <td
                      key={j}
                      title={`answer key ${VLABEL[c.labels[i]]}, model ${VLABEL[c.labels[j]]}: ${v} (${pct(share)})`}
                      className={cx("h-11 rounded-md text-center text-body-2-semibold tabular-nums", share > 0.5 ? "text-white" : "text-text-primary", i === j && "ring-1 ring-line-strong")}
                      style={{ background: `color-mix(in oklab, var(--rd-seq) ${Math.round(6 + share * 88)}%, var(--rd-card))` }}
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

function LossChart({ t }: { t: EvalResults["training"] }) {
  const data = useMemo(() => {
    const m = new Map<number, { step: number; train?: number; test?: number }>();
    t.loss_curve.forEach(([s, v]) => m.set(s, { ...(m.get(s) ?? { step: s }), train: v }));
    t.test_nll.forEach(([s, v]) => m.set(s, { ...(m.get(s) ?? { step: s }), test: v }));
    return [...m.values()].sort((a, b) => a.step - b.step);
  }, [t]);
  if (!data.length)
    return (
      <EmptyState icon={RiLineChartLine} tone="blue" title="Training run pending" className="py-10">
        The LoRA on {t.base_model} (rank {t.rank}) hasn&apos;t finished on Tinker yet. Train loss and held-out NLL plot here when it does.
      </EmptyState>
    );
  return (
    <div className="flex flex-col gap-2 px-5 pb-5">
      <div className="flex flex-wrap gap-4 text-caption-1-medium text-text-secondary">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded" style={{ background: "var(--rd-series-1)" }} aria-hidden /> Train loss
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: "var(--rd-series-2)" }} aria-hidden /> Test NLL (held-out recalls)
        </span>
      </div>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--rd-line)" />
            <XAxis dataKey="step" type="number" domain={["dataMin", "dataMax"]} tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--rd-line)" }} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
            <Tooltip {...TIP} labelFormatter={(s) => `step ${s}`} formatter={(v, n) => [typeof v === "number" ? v.toFixed(3) : String(v), n === "train" ? "train loss" : "test NLL"]} />
            <Line type="monotone" dataKey="train" stroke="var(--rd-series-1)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="test" stroke="var(--rd-series-2)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--rd-card)", fill: "var(--rd-series-2)" }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RiskChart({ models }: { models: Model[] }) {
  const data = models.map((m) => {
    const [a, b] = frac(m.risky_caught);
    const [c, d] = frac(m.false_alarms);
    return { name: short(m), caught: b ? a / b : 0, alarms: d ? c / d : 0, rc: m.risky_caught, fa: m.false_alarms };
  });
  return (
    <div className="flex flex-col gap-3 px-5 pb-5">
      <div className="flex flex-wrap gap-4 text-caption-1-medium text-text-secondary">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: "var(--rd-series-1)" }} aria-hidden /> Risky caught (higher is better)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: "var(--rd-series-2)" }} aria-hidden /> False alarms (lower is better)
        </span>
      </div>
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }} barGap={2} barCategoryGap="24%">
            <CartesianGrid vertical={false} stroke="var(--rd-line)" />
            <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--rd-line)" }} interval={0} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
            <Tooltip {...TIP} formatter={(v, n, p) => [`${pct(Number(v))} (${n === "caught" ? p.payload.rc : p.payload.fa})`, n === "caught" ? "Risky caught" : "False alarms"]} />
            <Bar dataKey="caught" fill="var(--rd-series-1)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            <Bar dataKey="alarms" fill="var(--rd-series-2)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function SingleBars({ models, value, format, label }: { models: Model[]; value: (m: Model) => number; format: (n: number) => string; label: string }) {
  const data = models.map((m) => ({ name: short(m), v: value(m), ours: m.role === "lora" }));
  return (
    <div className="h-[220px] w-full px-3 pb-4">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 56, bottom: 0, left: 8 }}>
          <CartesianGrid horizontal={false} stroke="var(--rd-line)" />
          <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} />
          <YAxis type="category" dataKey="name" tick={AXIS} tickLine={false} axisLine={false} width={88} />
          <Tooltip {...TIP} formatter={(v) => [format(Number(v)), label]} />
          <Bar dataKey="v" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false} label={{ position: "right", fontSize: 11, fill: "var(--color-text-secondary)", formatter: (v: unknown) => format(Number(v)) }}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.ours ? "var(--rd-m-ours)" : "var(--rd-series-1)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LabView() {
  const { data, loading, placeholder } = useLoad(getEval, "eval");
  const all = useMemo(() => [...((data?.models ?? []) as Model[])].sort((a, b) => rank(a.role) - rank(b.role)), [data]);
  const models = all.filter(ready);
  const pending = all.filter((m) => !ready(m));
  const lora = models.find((m) => m.role === "lora");
  // Headline = our student: the LoRA when it lands, else the best 4B baseline (never the teacher or the no-model rules).
  const best = lora ?? models.find((m) => m.role === "base_guided") ?? models.find((m) => m.role === "base");
  const teacher = models.find((m) => m.role === "teacher");
  const label = (role: string) => {
    const m = all.find((x) => x.role === role);
    return m ? roleLabel(m) : role;
  };
  // eval.json gold: "teacher + rule 7 by code (not human)" is the project's final answer key; only raw teacher
  // labels (no rule 7) are provisional.
  const goldS = data?.gold ?? "";
  const provisional = /provisional/i.test(goldS) || (/teacher/i.test(goldS) && !/rule 7/i.test(goldS));
  const notHuman = !!goldS && !/^human/i.test(goldS);

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Tinker · LoRA fine-tune
            </Pill>
            {provisional && <DemoBadge>Answer key is provisional</DemoBadge>}
            {notHuman && !provisional && (
              <Pill size="sm" tone="gray">
                Answer key: teacher + rule 7 · not human
              </Pill>
            )}
            <DemoBadge show={placeholder}>Placeholder numbers</DemoBadge>
          </>
        }
        title="Model Lab"
        description={
          data
            ? `The big model teaches, the small model reads. ${data.test_size} held-out (recall, listing) pairs from recalls the student never saw in training, graded against ${data.gold}. 10,000-sample bootstrap CIs; exact McNemar on discordant pairs.`
            : "Loading evaluation…"
        }
      />

      {loading || !data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-[320px] rounded-xl" />
          <Skeleton className="h-[320px] rounded-xl" />
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <KpiRow>
            <KpiCard index={0} icon={RiShieldCheckLine} tone="blue" label={`${best ? short(best) : "Best"} accuracy`} display={best ? pct(best.acc, 1) : "—"} status={lora ? "Ours" : "LoRA pending"} caption={best ? `95% CI ${pct(best.acc_ci[0])}–${pct(best.acc_ci[1])}` : undefined} />
            <KpiCard index={1} icon={RiFlaskLine} tone="green" label="Risky caught" display={best?.risky_caught ?? "—"} status="Recall" caption="Key match or check, flagged" />
            <KpiCard index={2} icon={RiCoinsLine} tone="amber" label="Cost / 1k checks" display={best ? usd(best.cost_per_1k_usd) : "—"} status="Tinker" caption={teacher ? `Teacher ${usd(teacher.cost_per_1k_usd)}` : undefined} />
            <KpiCard index={3} icon={RiTimerFlashLine} tone="gray" label="p50 latency" display={best ? `${Math.round(best.p50_latency_ms).toLocaleString()} ms` : "—"} status="Per pair" caption={teacher ? `Teacher ${Math.round(teacher.p50_latency_ms).toLocaleString()} ms` : undefined} />
          </KpiRow>

          {pending.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-line-strong bg-subtle px-4 py-3 text-body-2-regular text-text-secondary">
              <Pill size="sm" tone="amber" dot>
                Pending
              </Pill>
              {pending.map((m) => roleLabel(m)).join(", ")}: still training or evaluating. Shown here as soon as the numbers land; nothing is estimated.
            </div>
          )}

          <div className="grid items-start gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader title="Accuracy, with 95% CI" description="Exact-verdict accuracy on the held-out set. Hover a row for the interval." />
              <div className="px-4 pb-4">
                <AccuracyCI models={models} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Risky caught vs false alarms" description="Of the pairs that are risky (answer key match or check), how many each model flagged; and how often it flagged a clear one." />
              <RiskChart models={models} />
            </Card>
          </div>

          <div className="grid items-start gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title="Cost per 1,000 checks" icon={RiCoinsLine} description="USD, from token counts at Tinker prices" />
              <SingleBars models={models} value={(m) => m.cost_per_1k_usd} format={(n) => usd(n)} label="Cost / 1k" />
            </Card>
            <Card>
              <CardHeader title="Latency (p50)" icon={RiSpeedLine} description="Milliseconds per (recall, listing) pair" />
              <SingleBars models={models} value={(m) => m.p50_latency_ms} format={(n) => `${Math.round(n).toLocaleString()} ms`} label="p50 latency" />
            </Card>
          </div>

          <Card>
            <CardHeader title="Confusion matrices" description="Rows are the answer key (teacher + rule 7, not human); cell shade is the share of that row." />
            <div className="grid gap-6 px-5 pb-5 sm:grid-cols-2 xl:grid-cols-4">
              {Object.entries(data.confusion).map(([role, c]) => (
                <ConfusionGrid key={role} name={label(role)} c={c} />
              ))}
            </div>
          </Card>

          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader title="Training" description={`${data.training.base_model} · LoRA rank ${data.training.rank}${data.training.steps ? ` · ${data.training.steps} steps · lr ${data.training.lr}` : ""}`} />
              <LossChart t={data.training} />
            </Card>
            <Card>
              <CardHeader title="Paired tests" description="Same pairs, two models. p from exact McNemar on the pairs only one got right." />
              <div className="overflow-x-auto border-t border-line">
                <table className="w-full min-w-[480px] text-body-2-regular">
                  <thead>
                    <tr className="border-b border-line bg-subtle text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase">
                      <th className="h-10 px-5 text-start">A vs B</th>
                      <th className="px-3 text-end whitespace-nowrap">Gain (95% CI)</th>
                      <th className="px-3 text-end whitespace-nowrap">Only A / B</th>
                      <th className="px-5 text-end">p</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.paired.map((p) => (
                      <tr key={`${p.a}-${p.b}`} className="border-b border-line last:border-b-0">
                        <th scope="row" className="h-14 px-5 text-start font-medium text-text-primary">
                          {label(p.a)} <span className="text-text-tertiary">vs</span> {label(p.b)}
                        </th>
                        <td className="px-3 text-end tabular-nums">
                          <span className={cx("text-body-2-semibold", p.gain > 0 ? "text-clear-text" : "text-text-secondary")}>
                            {p.gain > 0 ? "+" : ""}
                            {(p.gain * 100).toFixed(1)} pts
                          </span>
                          <span className="block text-caption-2-regular text-text-tertiary">
                            [{(p.ci[0] * 100).toFixed(1)}, {(p.ci[1] * 100).toFixed(1)}]
                          </span>
                        </td>
                        <td className="px-3 text-end text-text-secondary tabular-nums">
                          {p.only_a} / {p.only_b}
                        </td>
                        <td className="px-5 text-end tabular-nums">
                          <span className={p.p < 0.05 ? "font-semibold text-text-primary" : "text-text-tertiary"}>{p.p < 0.001 ? "<0.001" : p.p.toFixed(3)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Every model, same test set" />
            <div className="overflow-x-auto border-t border-line">
              <table className="w-full min-w-[820px] text-body-2-regular">
                <thead>
                  <tr className="border-b border-line bg-subtle text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase">
                    <th className="h-10 px-5 text-start">Model</th>
                    <th className="px-3 text-end">Accuracy</th>
                    <th className="px-3 text-end">Macro F1</th>
                    <th className="px-3 text-end">Risky caught</th>
                    <th className="px-3 text-end">False alarms</th>
                    <th className="px-3 text-end">JSON valid</th>
                    <th className="px-3 text-end">p50</th>
                    <th className="px-5 text-end">Cost / 1k</th>
                  </tr>
                </thead>
                <tbody>
                  {all.map((m) => (
                    <tr key={m.role} className="border-b border-line last:border-b-0 hover:bg-hover">
                      <th scope="row" className="h-14 px-5 text-start font-medium text-text-primary">
                        <span className="flex flex-col">
                          <span>{roleLabel(m)}</span>
                          <code className="rd-mono text-caption-2-regular text-text-tertiary">{m.role}</code>
                        </span>
                      </th>
                      {ready(m) ? (
                        <>
                          <td className="px-3 text-end text-body-2-semibold text-text-primary tabular-nums">{pct(m.acc, 1)}</td>
                          <td className="px-3 text-end text-text-secondary tabular-nums">{m.macro_f1.toFixed(3)}</td>
                          <td className="px-3 text-end text-text-secondary tabular-nums">{m.risky_caught}</td>
                          <td className="px-3 text-end text-text-secondary tabular-nums">{m.false_alarms}</td>
                          <td className="px-3 text-end text-text-secondary tabular-nums">{pct(m.json_valid)}</td>
                          <td className="px-3 text-end text-text-secondary tabular-nums">{Math.round(m.p50_latency_ms).toLocaleString()} ms</td>
                          <td className="px-5 text-end text-text-secondary tabular-nums">{usd(m.cost_per_1k_usd)}</td>
                        </>
                      ) : (
                        <td colSpan={7} className="px-5 text-end">
                          <Pill size="sm" tone="amber" dot>
                            Pending
                          </Pill>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {data.examples.length > 0 && (
            <Card>
              <CardHeader title="Where the models disagree" description="Held-out pairs, answer key vs each model." />
              <ul className="flex flex-col border-t border-line">
                {data.examples.slice(0, 8).map((e) => (
                  <li key={e.pair_id} className="grid gap-3 border-b border-line px-5 py-3 last:border-b-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <p className="text-body-2-semibold text-text-primary">“{e.listing_title}”</p>
                      <p className="truncate text-caption-1-regular text-text-tertiary">vs {e.recall_title}</p>
                    </div>
                    <dl className="grid grid-cols-3 gap-2 md:w-[400px]">
                      {(
                        [
                          ["Key", e.gold],
                          ["Base", e.base],
                          ["LoRA", e.lora],
                        ] as const
                      ).map(([k, v]) => (
                        <div key={k} className="flex flex-col gap-1">
                          <dt className="text-caption-2-semibold text-text-tertiary">{k}</dt>
                          <dd>{v ? <VerdictPill verdict={v} size="sm" /> : <Pill size="sm">Pending</Pill>}</dd>
                        </div>
                      ))}
                    </dl>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <p className="text-caption-1-regular text-text-tertiary">
            Generated {formatDate(data.generated_at)} · answer key: {data.gold}. The blind label UI exists for a human audit but was not used for these numbers.
          </p>
        </div>
      )}
    </Page>
  );
}

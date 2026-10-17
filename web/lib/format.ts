import type { Verdict } from "./types";

export const VERDICT_LABEL: Record<Verdict, string> = {
  match: "Do not sell",
  check: "Check label",
  no_match: "Clear",
};

export const VERDICT_SHORT: Record<Verdict, string> = {
  match: "Match",
  check: "Check",
  no_match: "No match",
};

export function formatDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", opts);
}

/** "2024-06" → "Jun 2024" */
export function formatMonth(ym: string | null | undefined): string {
  if (!ym) return "—";
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(y, m - 1, 15).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function soldWindow(from: string | null | undefined, to: string | null | undefined): string {
  if (!from && !to) return "Not stated";
  if (from === to) return formatMonth(from);
  return `${formatMonth(from)} – ${formatMonth(to)}`;
}

export function durationMs(a: string | null | undefined, b: string | null | undefined): number | null {
  if (!a || !b) return null;
  const d = new Date(b).getTime() - new Date(a).getTime();
  return Number.isFinite(d) ? d : null;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Math.round((now - t) / 1000);
  const abs = Math.abs(diff);
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return fmt.format(-diff, "second");
  if (abs < 3600) return fmt.format(-Math.round(diff / 60), "minute");
  if (abs < 86400) return fmt.format(-Math.round(diff / 3600), "hour");
  return fmt.format(-Math.round(diff / 86400), "day");
}

export const num = (n: number) => n.toLocaleString("en-US");

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function usd(x: number): string {
  if (x === 0) return "$0";
  if (x < 0.1) return `$${x.toFixed(3)}`;
  return `$${x.toFixed(2)}`;
}

/** "x/y" → [x, y] */
export function frac(s: string): [number, number] {
  const [a, b] = s.split("/").map(Number);
  return [a || 0, b || 0];
}

/** "fetch_new_recalls" → "Fetch new recalls" */
export function stepLabel(name: string): { label: string; target?: string } {
  const [base, target] = name.split(":");
  return { label: base.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()), target };
}

export type StepFlag = "retried" | "resumed" | "snapshot" | null;

export function stepFlag(step: { attempt: number; error?: string | null; note?: string | null; status: string }): StepFlag {
  const e = (step.error ?? "").toLowerCase();
  if (/(crash|killed|resum|restarted worker)/.test(e)) return "resumed";
  if (step.attempt > 1 || step.status === "retrying" || /retr/.test(e)) return "retried";
  if (/snapshot/i.test(step.note ?? "")) return "snapshot";
  return null;
}

/** "Papablic, of USA Recalls Convertible Bedside Sleepers Due to Risk…" → "Convertible Bedside Sleepers" */
export function shortTitle(title: string): string {
  const m = title.match(/Recall(?:s|ed)?\s+(?:of\s+)?(.*?)\s+(?:Due to|Because)/i);
  if (m) return m[1].replace(/^(Over|More Than) [\d.,]+ (Million )?/i, "");
  const n = title.match(/^(.*?)\s+Recalled/i);
  return n ? n[1] : title;
}

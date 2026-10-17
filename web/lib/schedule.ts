/** WeeklyRecallSweep fires Thursdays 14:00 America/New_York (Temporal Schedule). */

function nyOffsetMinutes(at: Date): number {
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", timeZoneName: "shortOffset" })
      .formatToParts(at)
      .find((p) => p.type === "timeZoneName")?.value;
    const m = part?.match(/GMT([+-]\d{1,2})(?::(\d{2}))?/);
    if (m) return Number(m[1]) * 60 + (Number(m[1]) < 0 ? -1 : 1) * Number(m[2] ?? 0);
  } catch {
    /* fall through */
  }
  return -300;
}

function nyParts(at: Date) {
  const f = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", weekday: "short" });
  const p = Object.fromEntries(f.formatToParts(at).map((x) => [x.type, x.value]));
  return { y: Number(p.year), m: Number(p.month), d: Number(p.day), wd: p.weekday as string };
}

export function nextSweep(now = new Date()): Date {
  for (let i = 0; i < 8; i++) {
    const probe = new Date(now.getTime() + i * 86_400_000);
    const { y, m, d, wd } = nyParts(probe);
    if (wd !== "Thu") continue;
    const guess = new Date(Date.UTC(y, m - 1, d, 14, 0, 0));
    const at = new Date(guess.getTime() - nyOffsetMinutes(guess) * 60_000);
    if (at.getTime() > now.getTime()) return at;
  }
  return new Date(now.getTime() + 7 * 86_400_000);
}

export function countdown(to: Date, now = new Date()) {
  const ms = Math.max(0, to.getTime() - now.getTime());
  const d = Math.floor(ms / 86_400_000);
  const h = Math.floor((ms % 86_400_000) / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return { d, h, m, s, ms };
}

export function formatSweep(at: Date): string {
  return `${at.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "America/New_York" })} · 2:00 PM ET`;
}

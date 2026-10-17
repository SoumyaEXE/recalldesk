import { Fragment, type ReactNode } from "react";

const AUTO_ID = /\b(?=[A-Za-z0-9-]*\d)(?!(?:19|20)\d\d\b)(?:[A-Z0-9][A-Za-z0-9-]{3,}|\d{4,})\b|\bOET \d{5}\b/g;

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Wrap identifiers (model numbers, date/batch codes, UPCs) in a mark. With
 * `ids`, only those strings are highlighted; otherwise mixed letter+digit
 * tokens are auto-detected.
 */
export function HighlightIds({ text, ids, className = "rd-id-mark" }: { text: string; ids?: string[]; className?: string }): ReactNode {
  const list = (ids ?? []).filter((x) => x && x.length >= 3);
  const re = list.length ? new RegExp(`(${list.sort((a, b) => b.length - a.length).map(escapeRe).join("|")})`, "gi") : AUTO_ID;
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g"))) {
    const i = m.index ?? 0;
    if (i > last) out.push(text.slice(last, i));
    out.push(
      <mark key={i} className={className}>
        {m[0]}
      </mark>,
    );
    last = i + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <Fragment>{out}</Fragment>;
}

"use client";

import { useId, useState } from "react";
import { RiBrainLine, RiCheckLine, RiEditLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { postCorrection } from "@/lib/api";
import { VERDICT_LABEL } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import { cx } from "@/utils/cx";
import { VerdictGlyph } from "./verdict";

/**
 * "Not a match? / Correct this" — sends the shop's correction to Backboard as a
 * memory (POST /api/shops/{shop}/corrections) and shows the memory id it got.
 */
export function CorrectThis({ item, recallNumber, current, shopId, compact = false }: { item: string; recallNumber: string; current: Verdict; shopId?: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [verdict, setVerdict] = useState<Verdict>(current === "no_match" ? "check" : "no_match");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<{ memory_id: string; local: boolean } | null>(null);
  const noteId = useId();

  if (saved) {
    return (
      <p className="rd-no-print flex flex-wrap items-center gap-1.5 text-caption-1-medium text-text-secondary" role="status">
        <RiBrainLine className="size-3.5 text-accent-600" aria-hidden />
        Saved to shop memory
        <code className="rounded bg-background-secondary-default px-1 font-mono text-caption-1-medium text-text-primary">{saved.memory_id}</code>
        {saved.local && <span className="text-text-tertiary">(stored in this browser: API offline)</span>}
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cx(
          "rd-no-print inline-flex w-fit cursor-pointer items-center gap-1 rounded-md text-caption-1-medium text-ink underline decoration-dotted underline-offset-2 outline-none hover:decoration-solid focus-visible:ring-2 focus-visible:ring-border-focus-ring",
          compact && "text-caption-2-medium",
        )}
      >
        <RiEditLine className="size-3.5" aria-hidden />
        {current === "match" ? "Not a match? Correct this" : "Correct this"}
      </button>
    );
  }

  const options: Verdict[] = (["no_match", "check", "match"] as Verdict[]).filter((v) => v !== current);
  return (
    <form
      className="rd-no-print flex flex-col gap-2 rounded-xl border border-border-button-default bg-background-secondary-default p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        const res = await postCorrection(
          { listing_or_item: item, recall_number: recallNumber, correct_verdict: verdict, note: note.trim() || `${item}: ${VERDICT_LABEL[verdict].toLowerCase()} for recall ${recallNumber}` },
          shopId,
        );
        setBusy(false);
        setSaved({ memory_id: res.memory_id, local: res.source !== "live" });
      }}
    >
      <fieldset className="flex flex-wrap items-center gap-1.5">
        <legend className="mb-1.5 text-caption-1-semibold text-text-secondary">It should be</legend>
        {options.map((v) => (
          <label
            key={v}
            className={cx(
              "inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1 text-caption-1-semibold has-focus-visible:ring-2 has-focus-visible:ring-border-focus-ring",
              verdict === v ? "border-accent-500 bg-background-primary-default text-text-primary" : "border-border-button-default text-text-secondary hover:bg-background-primary-default",
            )}
          >
            <input type="radio" name={`v-${noteId}`} value={v} checked={verdict === v} onChange={() => setVerdict(v)} className="sr-only" />
            <VerdictGlyph verdict={v} className="size-3.5" />
            {v === "no_match" ? "Not this recall (clear)" : VERDICT_LABEL[v]}
          </label>
        ))}
      </fieldset>
      <label htmlFor={noteId} className="text-caption-1-semibold text-text-secondary">
        Note for next week <span className="font-normal text-text-tertiary">(saved as a shop memory)</span>
      </label>
      <textarea
        id={noteId}
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g. Ours is the 2019 model, label says HANS0001 — not recalled."
        className="w-full resize-y rounded-lg border border-border-button-default bg-background-primary-default px-2.5 py-2 text-body-2-regular text-text-primary outline-none placeholder:text-text-placeholder focus-visible:ring-2 focus-visible:ring-border-focus-ring"
      />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="small" leadingIcon={RiCheckLine} disabled={busy}>
          {busy ? "Saving…" : "Save correction"}
        </Button>
        <Button type="button" size="small" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

"use client";

/* eslint-disable @next/next/no-img-element */
import { useState } from "react";
import { RiImageLine } from "@remixicon/react";
import { cx } from "@/utils/cx";

/**
 * CPSC product photo, loaded eagerly with fixed dimensions (no layout shift).
 * A handful of CPSC image URLs are broken upstream (garbled filenames → 400 /
 * ORB-blocked), so failures fall back to a tile naming the product type.
 */
export function RecallImage({ src, label, size = 96, className, eager = true }: { src?: string | null; label: string; size?: number; className?: string; eager?: boolean }) {
  const [failed, setFailed] = useState(false);
  const box = cx("shrink-0 overflow-hidden rounded-lg border border-line bg-white", className);
  if (!src || failed) {
    return (
      <span className={cx(box, "flex flex-col items-center justify-center gap-1 bg-subtle p-1.5 text-center")} style={{ width: size, height: size }} role="img" aria-label={`No photo: ${label}`}>
        <RiImageLine className="size-5 text-foreground-icon-tertiary" aria-hidden />
        {size >= 72 && <span className="line-clamp-2 text-caption-2-medium text-text-tertiary capitalize">{label}</span>}
      </span>
    );
  }
  return (
    <img
      src={src}
      alt={label}
      width={size}
      height={size}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailed(true)}
      className={cx(box, "object-contain")}
      style={{ width: size, height: size }}
    />
  );
}
